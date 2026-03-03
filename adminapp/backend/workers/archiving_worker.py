import asyncio
import time
from backend.services.db_user import DBUser
from backend.services.log_manager import Logger
from backend.services.redis_client import RedisClient
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask
from sqlalchemy import select, update

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
        將超過 14 天的任務標記為已封存。
        
        判斷規則：
        - 三個結束時間欄位：test_end_ut、pre_test_end_ut、stop_time_new
        - NULL、0、-1 視為「該欄位不適用」，忽略不計入判斷
        - 有效值（> 0）的欄位，必須全部都超過 14 天，才執行封存
        - 如果三個欄位都是無效值，則不封存（無法判斷是否結束）
        """
        now = int(time.time())
        threshold_time = now - (14 * 86400)  # 14天 = 14 * 24 * 60 * 60

        # 撈出所有尚未封存的任務（含時間欄位，在 Python 端判斷）
        stmt = select(
            SendTask.sendtask_uuid,
            SendTask.test_end_ut,
            SendTask.pre_test_end_ut,
            SendTask.stop_time_new,
        ).where(SendTask.is_archived == False)
        
        # execute() 回傳完整 Result，.all() 取得 named tuple rows（支援 row.欄位名 存取）
        result = await db_controller.execute(stmt)
        all_active = result.all()

        candidates = []
        for row in all_active:
            # 將三個時間欄位的值蒐集起來，過濾掉 None、0、-1 等無效值
            time_fields = {
                "test_end_ut":     row.test_end_ut,
                "pre_test_end_ut": row.pre_test_end_ut,
                "stop_time_new":   row.stop_time_new,
            }
            valid_times = [v for v in time_fields.values() if v and v > 0]

            # 如果沒有任何有效時間欄位，無法判斷，跳過
            if not valid_times:
                continue

            # 所有有效欄位都必須超過 14 天
            if all(t < threshold_time for t in valid_times):
                candidates.append(row.sendtask_uuid)
        
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

