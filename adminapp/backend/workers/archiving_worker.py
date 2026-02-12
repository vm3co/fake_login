import asyncio
import time
from backend.services.db_user import DBUser
from backend.services.log_manager import Logger
from backend.services.redis_client import RedisClient
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask
from sqlalchemy import select, update, or_

logger = Logger().get_logger()

class ArchivingWorker:
    def __init__(self):
        self.db_user = DBUser()
        self.redis = RedisClient()

    async def start(self):
        """
        手動觸發封存檢查 (供排程器呼叫)
        """
        logger.info("ArchivingWorker job triggered.")
        try:
             await self.archive_old_tasks()
        except Exception as e:
             logger.error(f"ArchivingWorker error: {e}")

    async def archive_old_tasks(self):
        """
        將超過 14 天的任務標記為已封存
        """
        now = int(time.time())
        # 14天 = 14 * 24 * 60 * 60
        threshold_time = now - (14 * 86400)
        
        # 找出需要封存的任務 UUID
        stmt = select(SendTask.sendtask_uuid).where(
            SendTask.test_end_ut < threshold_time,
            or_(SendTask.stop_time_new < threshold_time, SendTask.stop_time_new.is_(None)),
            or_(SendTask.pre_test_end_ut < threshold_time, SendTask.pre_test_end_ut.is_(None)),
            SendTask.is_archived == False
        )
        candidates = await db_controller.execute_scalars(stmt)
        
        if not candidates:
            logger.info("No tasks to archive.")
            return

        # 1. 批次更新 DB
        stmt_update = update(SendTask).where(SendTask.sendtask_uuid.in_(candidates)).values(is_archived=True)
        await db_controller.execute(stmt_update)
        
        # 2. 清除 Redis Cache
        client = await self.redis.get_client()
        for uuid in candidates:
            # logger.info(f"Archiving task {uuid}...")
            # await client.delete(f"task:{uuid}:details")
             try:
                 await client.delete(f"task:{uuid}:details")
             except Exception as e:
                 logger.warning(f"Failed to delete redis cache for {uuid}: {e}")
            
        logger.info(f"Archived {len(candidates)} tasks.")

