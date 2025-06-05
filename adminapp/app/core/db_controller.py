import re
import asyncpg
import aiofiles

from app.services.log_manager import Logger


logger = Logger().get_logger()

class ApplianceDB:
    def __init__(self):
        self.db_pool = None
        self.allowed_tables = {"sendtasks", "accts", "users"}
        self.allowed_columns = {
            "sendtasks": {"sendtask_id", "sendtask_uuid", "sendtask_owner_gid", "sendtask_create_ut"},
            "accts": {"acct_id", "acct_uuid", "acct_email", "acct_full_name", "acct_full_name_2nd", "acct_activate", "orgs"},
            "users": {"username", "password_hash", "email", "full_name", "orgs", "create_time"}
        }

    async def db_init(self):
        """ 初始化資料庫連線池與資料表 """
        if self.db_pool is not None:
            return
        
        logger.debug("Initializing PostgreSQL connection pool...")
        # 使用 asyncpg 建立連線池
        self.db_pool = await asyncpg.create_pool(
            host='postgres-db',
            port=5432,
            user='myuser',
            password='mypassword',
            database='mydatabase',
            min_size=1,
            max_size=10
        )

        async with self.db_pool.acquire() as connection:
            with open("app/core/config/table_info.sql", mode="r") as f:
                schema_sql = f.read()
                for stmt in schema_sql.strip().split(";"):
                    stmt = stmt.strip()
                    if not stmt:
                        continue  # skip empty statements
                    await connection.execute(stmt)


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
            print(f"Database connection lost: {e}. Reinitializing...")
            await self.db_close()
            await self.db_init()

    async def table_exists(self, table_name: str) -> bool:
        """ 
        檢查 table 是否存在 
        :param table_name: 欲檢查的資料表名稱
        :return: 如果資料表存在，返回 True，否則返回 False
        """
        await self.check_db_connection()
        async with self.db_pool.acquire() as connection:
            query = "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = $1)"
            result = await connection.fetchval(query, table_name)
            return result
        
    async def table_empty(self, table_name: str) -> bool:
        """ 
        檢查 table 是否為空 
        :param table_name: 欲檢查的資料表名稱
        :return: 如果資料表為空，返回 True，否則返回 False
        """
        await self.check_db_connection()
        async with self.db_pool.acquire() as connection:
            query = f"SELECT COUNT(*) FROM \"{table_name}\""
            count = await connection.fetchval(query)
            return count == 0

    async def create_table(self, table_name: str, columns: dict):
        """
        建立新資料表。
        :param table_name: 欲建立的資料表名稱
        :param columns: 欄位定義，格式為 {"column_name": "DATA_TYPE", ...}
                        例如 {"id": "SERIAL PRIMARY KEY", "name": "TEXT", "age": "INT"}
        """
        if not table_name or not isinstance(columns, dict) or not columns:
            raise ValueError("請提供有效的 table_name 與欄位定義 dict。")

        await self.check_db_connection()

        # 避免 SQL Injection: 僅允許英數底線開頭的命名
        if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
            raise ValueError("不合法的資料表名稱")

        for col in columns:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col.strip('"')):
                raise ValueError(f"不合法的欄位名稱：{col}")

        col_defs = ', '.join(f"{col} {dtype}" for col, dtype in columns.items())
        sql_cmd = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs});'

        async with self.db_pool.acquire() as connection:
            await connection.execute(sql_cmd)
            logger.info(f"Table `{table_name}` created successfully.")
        # 加入白名單允許
        self.allowed_tables.add(table_name)
        self.allowed_columns[table_name] = set(columns.keys())

    async def clear_table(self, table_name: str):
        """ 清空整個資料表 """
        await self.check_db_connection()
        async with self.db_pool.acquire() as connection:
            sql_cmd = f'DELETE FROM "{table_name}"'
            await connection.execute(sql_cmd)

    async def get_db(self, table_name: str, column_names: list[str] = None, value: str = None, include_inactive: bool = False) -> list:
        """
        查詢資料，支援全表查詢、欄位篩選與條件查詢。
        - 預設只查 is_active = TRUE 的資料。
        - 若需包含停用資料，或是不含is_active，請傳入 include_inactive=True。
        - 安全查詢資料，含欄位與表格名稱白名單限制
        """
        await self.check_db_connection()

        # 檢查白名單
        # if table_name not in self.allowed_tables:
        #     raise ValueError("Invalid table name.")
        # valid_columns = self.allowed_columns.get(table_name, set())
        # if column_names:
        #     if not set(column_names).issubset(valid_columns):
        #         raise ValueError("Invalid column(s) in select_columns.")

        async with self.db_pool.acquire() as connection:
            if column_names and value: 
                # 查詢指定欄位 = 值，並可選擇是否包含停用資料
                sql_cmd = f'SELECT * FROM "{table_name}" WHERE {column_names[0]} = $1'
                sql_cmd = sql_cmd + " AND is_active = TRUE" if not include_inactive else sql_cmd
                result = await connection.fetch(sql_cmd, value)
            elif column_names:
                col_str = ", ".join(column_names)
                sql_cmd = f'SELECT {col_str} FROM "{table_name}"'
                sql_cmd = sql_cmd + " WHERE is_active = TRUE" if not include_inactive else sql_cmd
                result = await connection.fetch(sql_cmd)
            else:
                sql_cmd = f'SELECT * FROM "{table_name}"'
                sql_cmd = sql_cmd + " WHERE is_active = TRUE" if not include_inactive else sql_cmd
                result = await connection.fetch(sql_cmd)
            return [dict(row) for row in result] if result else []

    async def insert_db(self, table_name: str, data: dict | list[dict]):
        """ 單筆或批次插入資料，並自動分批避免 asyncpg 限制 """
        if not data:
            return None

        await self.check_db_connection()

        async with self.db_pool.acquire() as connection:
            if isinstance(data, dict):
                columns = list(data.keys())
                col_str = ', '.join(columns)
                placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
                sql_cmd = f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders}) RETURNING *'
                result = await connection.fetchrow(sql_cmd, *data.values())
                return dict(result) if result else None

            elif isinstance(data, list) and all(isinstance(item, dict) for item in data):
                if not data:
                    return []

                # 統一取第一筆欄位當作共通欄位（強制比對）
                columns = list(data[0].keys())
                col_str = ', '.join(columns)

                max_params = 30000  # asyncpg 限制32767，這邊保守估算
                max_rows_per_batch = max(1, max_params // len(columns))

                results = []

                for i in range(0, len(data), max_rows_per_batch):
                    batch = data[i:i + max_rows_per_batch]

                    all_values = []
                    value_placeholders = []

                    for j, item in enumerate(batch):
                        # 強制使用 columns 順序來取值
                        values = [item.get(col) for col in columns]
                        all_values.extend(values)

                        start_index = j * len(columns)
                        placeholders = [f'${start_index + k + 1}' for k in range(len(columns))]
                        value_placeholders.append(f"({', '.join(placeholders)})")

                    sql_cmd = f'INSERT INTO "{table_name}" ({col_str}) VALUES {", ".join(value_placeholders)} RETURNING *'
                    batch_result = await connection.fetch(sql_cmd, *all_values)
                    results.extend([dict(r) for r in batch_result])

                return results

            else:
                raise TypeError("data 必須是 dict 或 list[dict]")

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

    async def upsert_db(self, table_name: str, data: dict, conflict_keys: list[str]):
        """
        有就更新，沒有就新增（PostgreSQL ON CONFLICT）。
        :param table_name: 資料表名稱
        :param data: 欲 upsert 的 dict
        :param conflict_keys: 唯一鍵欄位名稱 list
        """
        await self.check_db_connection()
        columns = list(data.keys())
        col_str = ', '.join(columns)
        placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
        update_str = ', '.join(f"{col}=EXCLUDED.{col}" for col in columns if col not in conflict_keys)
        conflict_str = ', '.join(conflict_keys)
        sql_cmd = (
            f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str} RETURNING *'
        )
        async with self.db_pool.acquire() as connection:
            result = await connection.fetchrow(sql_cmd, *data.values())
            return dict(result) if result else None

    async def delete_db(self, table_name: str, condition: dict):
        """ 刪除資料 """
        await self.check_db_connection()
        async with self.db_pool.acquire() as connection:
            condition_clause = ' AND '.join(f"{key} = ${i+1}" for i, key in enumerate(condition.keys()))
            sql_cmd = f'DELETE FROM "{table_name}" WHERE {condition_clause} RETURNING *'
            result = await connection.fetchrow(sql_cmd, *condition.values())
            if not result:
                raise ValueError(f"Operation failed on {table_name}, possibly due to missing matching records.")
            
            return dict(result) if result else None
