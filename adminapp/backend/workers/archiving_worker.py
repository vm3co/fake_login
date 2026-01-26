import asyncio
import time
from backend.services.db_user import DBUser
from backend.services.log_manager import Logger
from backend.services.redis_client import RedisClient

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
        
        # 找出 test_end_ut, stop_time_new, pre_test_end_ut 早於 threshold 且尚未封存的任務
        # 1. test_end_ut < threshold
        # 2. stop_time_new < threshold (or NULL)
        # 3. pre_test_end_ut < threshold (or NULL)
        
        where_clauses = [
            f"test_end_ut < {threshold_time}",
            f"(stop_time_new < {threshold_time} OR stop_time_new IS NULL)",
            f"(pre_test_end_ut < {threshold_time} OR pre_test_end_ut IS NULL)",
            "is_archived = FALSE"
        ]

        candidates = await self.db_user.db.get_db(
            "sendtasks", 
            select_columns=["sendtask_uuid"], 
            where_clauses=where_clauses
        )
        
        if not candidates:
            logger.info("No tasks to archive.")
            return

        client = await self.redis.get_client()
        
        for task in candidates:
            uuid = task["sendtask_uuid"]
            logger.info(f"Archiving task {uuid}...")
            
            # 1. 更新 DB
            await self.db_user.db.update_db("sendtasks", {"is_archived": True}, {"sendtask_uuid": uuid})
            
            # 2. 清除 Redis Cache (下次讀取時會設為短 TTL)
            await client.delete(f"task:{uuid}:details")
            
        logger.info(f"Archived {len(candidates)} tasks.")

