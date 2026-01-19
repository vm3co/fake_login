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
        self.running = False
        # 每天檢查一次
        self.check_interval = 86400 

    async def start(self):
        self.running = True
        logger.info("ArchivingWorker started.")
        await asyncio.sleep(10) # 啟動後等待一下再跑

        while self.running:
            try:
                logger.info("ArchivingWorker running archiving job...")
                await self.archive_old_tasks()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"ArchivingWorker error: {e}")
                await asyncio.sleep(3600)

    async def archive_old_tasks(self):
        """
        將超過 14 天的任務標記為已封存
        """
        now = int(time.time())
        # 14天 = 14 * 24 * 60 * 60
        threshold_time = now - (14 * 86400)
        
        # 找出 create_time 早於 threshold 且尚未封存的任務
        # sendtask_create_ut 是 timestamp (seconds or milliseconds? 根據 table_info 是 BIGINT, 假設 seconds)
        # 需確認 sendtask_create_ut 單位。假設是 seconds。
        
        candidates = await self.db_user.db.get_db(
            "sendtasks", 
            select_columns=["sendtask_uuid"], 
            where_clauses=[f"sendtask_create_ut < {threshold_time}", "is_archived = FALSE"]
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

    async def stop(self):
        self.running = False
        logger.info("ArchivingWorker stopping...")
