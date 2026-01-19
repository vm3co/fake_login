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
                # 這裡可以實作更複雜的同步邏輯，例如每10分鐘檢查所有 Active Task
                # 簡單起見，我們調用 refresh_sendlog_stats，它內部會呼叫 check_sendlog -> 觸發同步
                
                # 1. 獲取所有 active tasks
                active_tasks = await self.db_user.db.get_db("sendtasks", select_columns=["sendtask_uuid"], where_clauses=["is_archived = FALSE"])
                uuids = [t["sendtask_uuid"] for t in active_tasks]
                
                if uuids:
                    logger.info(f"SyncWorker checking {len(uuids)} active tasks...")
                    await self.db_user.refresh_sendlog_stats(uuids=uuids)
                    
                    # 2. 刷新快取 (Optional, refresh_sendlog_stats 更新了 DB, 但 Cache 可能還是舊的)
                    # 可以在 check_sendlog 更新 DB 後順便刪除 Cache，或者在這裡強制刷新
                    # 簡單作法：刪除 Cache，讓下一次讀取 Lazy Load
                    client = await self.redis.get_client()
                    for uuid in uuids:
                         await client.delete(f"task:{uuid}:details")
                
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"SyncWorker error: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        self.running = False
        logger.info("SyncWorker stopping...")
