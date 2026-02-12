import asyncio
import json
from app.services.redis_client import RedisClient
from sqlalchemy import update, select, func
from app.repository.models import SendLogDetail
from app.repository.db_controller import db_controller
from app.services.log_manager import Logger

logger = Logger().get_logger()

class PersistenceWorker:
    def __init__(self):
        self.redis = RedisClient()
        self.running = False
        self.batch_size = 10
        self.sleep_interval = 1 # seconds

    async def start(self):
        self.running = True
        logger.info("PersistenceWorker started.")
        while self.running:
            try:
                client = await self.redis.get_client()
                # 使用 BLPOP 阻塞式讀取，timeout 設為 5 秒
                # 這樣可以減少空迴圈
                result = await client.blpop("buffer:trigger_events", timeout=5)
                
                if result:
                    # result 格式: ('buffer:trigger_events', '{"type":...}')
                    _, data_str = result
                    await self.process_event(json.loads(data_str))
                
                # 如果需要批次處理，可以在這裡累積 list 再一次寫入，
                # 但目前為了即時性，先逐筆處理 (因為使用 array_append 針對單一 row)

            except Exception as e:
                logger.error(f"PersistenceWorker error: {e}")
                await asyncio.sleep(5) # 發生錯誤時暫停一下

    async def process_event(self, event: dict):
        event_type = event.get("type")
        uuid = event.get("uuid") # 這是 sendtasks 中的 uuid (對應 send_log_details.uuid)
        
        # 為了安全，檢查 uuid
        if not uuid:
            return

        try:
            if event_type == "visit":
                await self._process_visit(event)
            elif event_type == "qr_visit":
                await self._process_qr_visit(event)
            elif event_type == "input":
                await self._process_input(event)
            else:
                logger.warning(f"Unknown event type: {event_type}")
        except Exception as e:
            logger.error(f"Failed to process event {event}: {e}")

    async def _process_visit(self, event):
        try:
            stmt = update(SendLogDetail).where(SendLogDetail.uuid == event["uuid"]).values(
                second_access_time=func.array_append(func.coalesce(SendLogDetail.second_access_time, []), event["timestamp"]),
                second_access_src=func.array_append(func.coalesce(SendLogDetail.second_access_src, []), event["ip"]),
                second_access_dev=func.array_append(func.coalesce(SendLogDetail.second_access_dev, []), event["user_agent"])
            )
            result = await db_controller.execute(stmt)
            
            if result.rowcount == 0:
                logger.warning(f"No row found for uuid {event['uuid']} to update visit.")
            else:
                logger.info(f"Processed visit event for {event['uuid']}")
        except Exception as e:
            logger.error(f"Error processing visit event: {e}")
        
        if event.get("sendtask_uuid"):
             await self._invalidate_cache(event["sendtask_uuid"])
        elif len(event["uuid"]) == 32:
             await self._invalidate_cache_by_db(event["uuid"])

    async def _process_qr_visit(self, event):
        try:
            stmt = update(SendLogDetail).where(SendLogDetail.uuid == event["uuid"]).values(
                second_qrcode_time=func.array_append(func.coalesce(SendLogDetail.second_qrcode_time, []), event["timestamp"]),
                second_qrcode_src=func.array_append(func.coalesce(SendLogDetail.second_qrcode_src, []), event["ip"]),
                second_qrcode_dev=func.array_append(func.coalesce(SendLogDetail.second_qrcode_dev, []), event["user_agent"])
            )
            result = await db_controller.execute(stmt)
            logger.info(f"Processed qr_visit event for {event['uuid']}")
        except Exception as e:
            logger.error(f"Error processing qr_visit event: {e}")
        
        if event.get("sendtask_uuid"):
             await self._invalidate_cache(event["sendtask_uuid"])
        elif len(event["uuid"]) == 32:
             await self._invalidate_cache_by_db(event["uuid"])

    async def _process_input(self, event):
        try:
            stmt = update(SendLogDetail).where(SendLogDetail.uuid == event["uuid"]).values(
                second_input_time=func.array_append(func.coalesce(SendLogDetail.second_input_time, []), event["timestamp"]),
                second_input_src=func.array_append(func.coalesce(SendLogDetail.second_input_src, []), event["ip"]),
                second_input_dev=func.array_append(func.coalesce(SendLogDetail.second_input_dev, []), event["user_agent"]),
                second_input_info=func.array_append(func.coalesce(SendLogDetail.second_input_info, []), event["data"])
            )
            result = await db_controller.execute(stmt)
            logger.info(f"Processed input event for {event['uuid']}")
        except Exception as e:
            logger.error(f"Error processing input event: {e}")
        
        if event.get("sendtask_uuid"):
             await self._invalidate_cache(event["sendtask_uuid"])
        elif len(event["uuid"]) == 32:
             # Fallback: if somehow we didn't get it (shouldn't happen with new router code)
             await self._invalidate_cache_by_db(event["uuid"])

    async def _invalidate_cache(self, sendtask_uuid: str):
        """
        直接清除 Redis Cache
        """
        try:
            cache_key = f"task:{sendtask_uuid}:details"
            client = await self.redis.get_client()
            await client.delete(cache_key)
            logger.info(f"Invalidated cache for task {sendtask_uuid}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for task {sendtask_uuid}: {e}")

    async def _invalidate_cache_by_db(self, uuid: str):
        """
        舊方法：根據 uuid (recipient ID) 查詢 sendtask_uuid
        """
        try:
             # 1. 查詢 sendtask_uuid
             stmt = select(SendLogDetail.sendtask_uuid).where(SendLogDetail.uuid == uuid)
             result = await db_controller.execute_scalars(stmt)
             sendtask_uuid = result[0] if result else None
                 
                 if sendtask_uuid:
                     await self._invalidate_cache(sendtask_uuid)
                 else:
                     logger.warning(f"Could not find sendtask_uuid for uuid {uuid}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache by db for {uuid}: {e}")

    async def stop(self):
        self.running = False
        logger.info("PersistenceWorker stopping...")
