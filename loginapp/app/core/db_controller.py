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
            print(f"Database connection lost: {e}. Reinitializing...")
            await self.db_close()
            await self.db_init()

    async def get_db(self, table_name: str, person_uuid: str, column_names: list[str] = None) -> list:
        """
        查詢資料，支援全表查詢、欄位篩選與條件查詢。
        """
        await self.check_db_connection()

        async with self.db_pool.acquire() as connection:
            # 查詢指定欄位 = 值
            col_str = ", ".join(column_names)
            sql_cmd = f'SELECT {col_str} FROM "{table_name}" WHERE uuid = $1'
            result = await connection.fetch(sql_cmd, person_uuid)
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


db = ApplianceDB()
