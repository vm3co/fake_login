# -*- coding: utf-8 -*-
'''
資料庫控制模組，提供資料庫連線、初始化、關閉、檢查連線等功能。
此模組使用 asyncpg 連接 PostgreSQL 資料庫，並提供基本的資料表操作功能。
支援的資料表包括 sendtasks、accts、users 等，並提供建立新資料表、清空資料表、檢查資料表是否存在等功能。
'''

from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Sequence, Type
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Select

from backend.repository.database import async_session
from backend.services.log_manager import Logger
from backend.repository.models import (
    User, SendTask, SendLogDetail, SendLogStats, Acct, 
    CustomerAcct, Mtmpl, Notification, LoginLog, TriggerPage
)

logger = Logger().get_logger()

ModelType = TypeVar("ModelType")

class DBController:
    """
    通用資料庫控制器，封裝基本的 CRUD 操作。
    """
    
    TABLE_MAPPING = {
        "users": User,
        "sendtasks": SendTask,
        "send_log_details": SendLogDetail,
        "sendlog_stats": SendLogStats,
        "accts": Acct,
        "customer_accts": CustomerAcct,
        "mtmpl": Mtmpl,
        "notifications": Notification,
        "login_logs": LoginLog,
        "trigger_pages": TriggerPage
    }

    def get_session(self) -> AsyncSession:
        """取得一個新的 AsyncSession Context Manager"""
        return async_session()

    async def execute(self, stmt: Any) -> Any:
        """
        執行傳入的 SQLAlchemy statement (Generic execution)
        """
        async with self.get_session() as session:
            try:
                result = await session.execute(stmt)
                await session.commit()
                return result
            except Exception as e:
                logger.error(f"Execute failed: {e}")
                await session.rollback()
                raise e

    async def execute_scalars(self, stmt: Any) -> List[Any]:
        """
        執行傳入的 SQLAlchemy statement 並回傳 scalars().all()
        """
        async with self.get_session() as session:
            try:
                result = await session.execute(stmt)
                await session.commit() 
                return result.scalars().all()
            except Exception as e:
                logger.error(f"Execute scalars failed: {e}")
                await session.rollback()
                raise e

    async def get(
        self, 
        model: Type[ModelType], 
        filters: Dict[str, Any] = None, 
        limit: int = None, 
        offset: int = None,
        order_by: Any = None
    ) -> List[ModelType]:
        """
        通用查詢方法
        :param model: SQLAlchemy Model 類別
        :param filters: 篩選條件 (Dict) e.g. {"username": "admin"}
        :param limit: 限制筆數
        :param offset: 偏移量
        :param order_by: 排序欄位
        :return: Model 物件列表
        """
        async with self.get_session() as session:
            stmt = select(model)
            if filters:
                for key, value in filters.items():
                    if hasattr(model, key):
                        column = getattr(model, key)
                        if isinstance(value, list):
                            stmt = stmt.where(column.in_(value))
                        else:
                            stmt = stmt.where(column == value)
            
            if order_by is not None:
                stmt = stmt.order_by(order_by)

            if limit:
                stmt = stmt.limit(limit)
            if offset:
                stmt = stmt.offset(offset)

            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_one(self, model: Type[ModelType], filters: Dict[str, Any]) -> Optional[ModelType]:
        """
        取得單一物件
        """
        results = await self.get(model, filters, limit=1)
        return results[0] if results else None

    async def create(self, model: Type[ModelType], data: Dict[str, Any]) -> ModelType:
        """
        建立新物件
        :param model: Model 類別
        :param data: 欄位資料 (Dict)
        :return: 建立後的 Model 物件
        """
        async with self.get_session() as session:
            try:
                obj = model(**data)
                session.add(obj)
                await session.commit()
                await session.refresh(obj)
                return obj
            except Exception as e:
                logger.error(f"Create failed: {e}")
                await session.rollback()
                raise e

    async def update(
        self, 
        model: Type[ModelType], 
        filters: Dict[str, Any], 
        data: Dict[str, Any]
    ) -> int:
        """
        更新物件
        :param model: Model 類別
        :param filters: 篩選條件
        :param data: 更新資料
        :return: 更新筆數
        """
        if not data:
            return 0
            
        async with self.get_session() as session:
            try:
                stmt = update(model)
                
                conditions = []
                for key, value in filters.items():
                    if hasattr(model, key):
                        column = getattr(model, key)
                        if isinstance(value, list):
                            conditions.append(column.in_(value))
                        else:
                            conditions.append(column == value)
                
                if conditions:
                    from sqlalchemy import and_
                    stmt = stmt.where(and_(*conditions))
                
                stmt = stmt.values(**data)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
            except Exception as e:
                logger.error(f"Update failed: {e}")
                await session.rollback()
                raise e

    async def delete(self, model: Type[ModelType], filters: Dict[str, Any]) -> int:
        """
        刪除物件
        :param model: Model 類別
        :param filters: 篩選條件
        :return: 刪除筆數
        """
        async with self.get_session() as session:
            try:
                stmt = delete(model)
                conditions = []
                for key, value in filters.items():
                    if hasattr(model, key):
                        column = getattr(model, key)
                        if isinstance(value, list):
                            conditions.append(column.in_(value))
                        else:
                            conditions.append(column == value)
                
                if conditions:
                    from sqlalchemy import and_
                    stmt = stmt.where(and_(*conditions))

                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
            except Exception as e:
                logger.error(f"Delete failed: {e}")
                await session.rollback()
                raise e
    
    async def batch_create(self, model: Type[ModelType], data_list: List[Dict[str, Any]]) -> int:
        """
        批次建立
        """
        if not data_list:
            return 0

        async with self.get_session() as session:
            try:
                objects = [model(**data) for data in data_list]
                session.add_all(objects)
                await session.commit()
                return len(objects)
            except Exception as e:
                logger.error(f"Batch create failed: {e}")
                await session.rollback()
                raise e

    async def upsert(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        index_elements: List[str],
        update_columns: List[str] = None
    ) -> int:
        """
        PostgreSQL Upsert (Insert on Conflict Update)
        :param model: Model 類別
        :param data_list: 資料列表 (List of Dicts)
        :param index_elements: 衝突判斷欄位 (例如 ['uuid'])
        :param update_columns: 需要更新的欄位列表。若為 None，則更新 data 中的所有欄位。
        """
        if not data_list:
            return 0
            
        async with self.get_session() as session:
            try:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                
                count = 0
                for data in data_list:
                    stmt = pg_insert(model).values(data)
                    
                    if update_columns:
                        # 只更新指定欄位
                        # 注意: excluded 是一個特殊的 alias，代表 "欲插入的該列資料"
                        set_dict = {col: getattr(stmt.excluded, col) for col in update_columns}
                    else:
                        # 更新所有提供的欄位
                        set_dict = data
                    
                    stmt = stmt.on_conflict_do_update(
                        index_elements=index_elements,
                        set_=set_dict
                    )
                    await session.execute(stmt)
                    count += 1
                
                await session.commit()
                return count
            except Exception as e:
                logger.error(f"Upsert failed: {e}")
                await session.rollback()
                raise e

    async def get_all_by_tablename(self, table_name: str) -> List[Dict[str, Any]]:
        """
        根據 table_name 取得所有資料 (Safe, No SQL Injection)
        :param table_name: 資料表名稱 (必須在 TABLE_MAPPING 中)
        :return: List of Dicts
        """
        if table_name not in self.TABLE_MAPPING:
             logger.error(f"Invalid table name request: {table_name}")
             raise ValueError(f"Invalid table name: {table_name}")
        
        model = self.TABLE_MAPPING[table_name]
        results = await self.get(model)
        
        # Convert to list of dicts
        return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in results]


# Global instance
db_controller = DBController()
