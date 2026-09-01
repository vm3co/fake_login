# -*- coding: utf-8 -*-
'''
資料庫控制模組 (TriggerApp Version)
'''

from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Sequence, Type
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Select

from app.repository.database import async_session
from app.services.log_manager import Logger

logger = Logger().get_logger()

ModelType = TypeVar("ModelType")

class DBController:
    """
    通用資料庫控制器，封裝基本的 CRUD 操作。
    """

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
                        set_dict = {col: getattr(stmt.excluded, col) for col in update_columns}
                    else:
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


# Global instance
db_controller = DBController()
