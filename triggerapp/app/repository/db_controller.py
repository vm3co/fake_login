import re
import asyncpg
import aiofiles

from app.services.log_manager import Logger


logger = Logger().get_logger()

class ApplianceDB:
    def __init__(self):
        self.db_pool = None
        self.allowed_tables = {"sendtasks"}
        self.allowed_columns = {
            "sendtasks": {"sendtask_id", "sendtask_uuid", "sendtask_create_ut"}
        }

    async def db_init(self):
        if self.db_pool is None:
            logger.debug("Initializing PostgreSQL connection pool...")
            self.db_pool = await asyncpg.create_pool(
                host='postgres-db',
                port=5432,
                user='myuser',
                password='mypassword',
                database='mydatabase',
                min_size=1,
                max_size=10
            )

    async def db_close(self):
        if self.db_pool:
            logger.debug("Closing PostgreSQL connection pool...")
            await self.db_pool.close()
            self.db_pool = None

    async def check_db_connection(self):
        """ 檢查資料庫連線，若斷線則重新初始化 """
        if self.db_pool is None:
            await self.db_init()
            return

        try:
            async with self.db_pool.acquire() as connection:
                await connection.fetch("SELECT 1")
        except Exception as e:
            logger.error(f"Database connection lost: {e}. Reinitializing...")
            await self.db_close()
            await self.db_init()

    async def get_db(self, table_name: str, person_uuid: str = None, column_names: list[str] = None, select_columns: list[str] = None, where_column: str = None, values: str | list[str] = None, where_clauses: list[str] = None, order_by: str = None) -> list:
        """
        查詢資料，支援全表查詢、欄位篩選與條件查詢。
        (為了相容舊介面，保留 person_uuid, column_names，但建議改用新介面參數)
        """
        await self.check_db_connection()

        # 欄位處理
        if select_columns:
            col_str = ', '.join(select_columns)
        else:
            col_str = '*'

        # 條件處理
        where_clause = ''
        bind_values = []

        if where_clauses:
             where_clause = " WHERE " + " AND ".join(where_clauses)
        elif where_column and values is not None:

            if not isinstance(values, list):
                values = [values]
            if not values:
                 # 若 values 為空，回傳空結果
                 return []
            
            placeholders = ', '.join(f'${i+1}' for i in range(len(values)))
            where_clause = f' WHERE "{where_column}" IN ({placeholders})'
            bind_values = values
            
        # Order By 處理
        order_sql = ""
        if order_by:
             if not re.match(r"^[a-zA-Z0-9_, ]+$", order_by):
                  raise ValueError("Illegal order_by string")
             order_sql = f" ORDER BY {order_by}"

        sql_cmd = f'SELECT {col_str} FROM "{table_name}"{where_clause}{order_sql}'

        async with self.db_pool.acquire() as connection:
            result = await connection.fetch(sql_cmd, *bind_values)
            return [dict(row) for row in result] if result else []

    async def update_db(self, table_name: str, data: dict, condition: dict):
        """ 更新資料 """
        await self.check_db_connection()
        async with self.db_pool.acquire() as connection:
            set_clause = ', '.join(f"{key} = ${i+1}" for i, key in enumerate(data.keys()))
            condition_clause = ' AND '.join(f"{key} = ${len(data) + i+1}" for i, key in enumerate(condition.keys()))
            sql_cmd = f'UPDATE "{table_name}" SET {set_clause} WHERE {condition_clause} RETURNING *'
            result = await connection.fetchrow(sql_cmd, *data.values(), *condition.values())
            if not result:
                raise ValueError(f"Operation failed on {table_name}, possibly due to missing matching records.")
            
            return dict(result) if result else None

    async def update_array_append(self, table_name: str, append_data: dict, condition: dict):
        """
        將資料 Append 到指定的 Array 欄位中 (Atomic Operation)
        """
        await self.check_db_connection()
        
        # 簡單驗證欄位名稱
        for col in append_data.keys():
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                raise ValueError(f"Illegal column name: {col}")

        async with self.db_pool.acquire() as connection:
            set_clauses = []
            values = []
            
            for i, (col, val) in enumerate(append_data.items()):
                set_clauses.append(f'"{col}" = array_append(COALESCE("{col}", \'{{}}\'), ${i+1})')
                values.append(val)
                
            condition_clauses = []
            base_idx = len(values)
            for i, (col, val) in enumerate(condition.items()):
                 condition_clauses.append(f'"{col}" = ${base_idx + i + 1}')
                 values.append(val)
            
            set_sql = ", ".join(set_clauses)
            condition_sql = " AND ".join(condition_clauses)
            
            sql_cmd = f'UPDATE "{table_name}" SET {set_sql} WHERE {condition_sql} RETURNING *'
            
            result = await connection.fetchrow(sql_cmd, *values)
            return dict(result) if result else None




db = ApplianceDB()
