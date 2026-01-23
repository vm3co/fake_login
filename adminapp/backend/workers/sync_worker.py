import asyncio
import pandas as pd
from backend.services.db_user import DBUser
from backend.services.getSe2data import get_se2_data
from backend.services.log_manager import Logger
from backend.services.redis_client import RedisClient

logger = Logger().get_logger()

# 簡化版 SyncWorker，主要功能是定期檢查已知的 task 是否有更新，以及是否有新 task (這邊先專注於現有 task 同步)
# 完整邏輯應該包含定期從 SE2 抓取 task list

class SyncWorker:
    def __init__(self):
        self.db_user = DBUser()
        self.redis = RedisClient()
        self.running = False
        self.check_interval = 600 # 10 minutes

    async def start(self):
        self.running = True
        logger.info("SyncWorker started.")
        while self.running:
            try:
                # 獲取所有 active tasks
                active_tasks = await self.db_user.db.get_db("sendtasks", select_columns=["sendtask_uuid"], where_clauses=["is_archived = FALSE"])
                uuids = [t["sendtask_uuid"] for t in active_tasks]
                
                if uuids:
                    logger.info(f"SyncWorker checking {len(uuids)} active tasks...")
                    await self.db_user.refresh_sendlog_stats(uuids=uuids)
                
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"SyncWorker error: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        self.running = False
        logger.info("SyncWorker stopping...")
