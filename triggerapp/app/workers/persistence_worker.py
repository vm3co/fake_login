import asyncio
import json
from app.services.redis_client import RedisClient
from app.repository.db_controller import db
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
            elif event_type == "input":
                await self._process_input(event)
            else:
                logger.warning(f"Unknown event type: {event_type}")
        except Exception as e:
            logger.error(f"Failed to process event {event}: {e}")

    async def _process_visit(self, event):
        await db.update_array_append(
            table_name="send_log_details",
            append_data={
                "second_access_time": event["timestamp"],
                "second_access_src": event["ip"],
                "second_access_dev": event["user_agent"]
            },
            condition={"uuid": event["uuid"]}
        )
        logger.debug(f"Processed visit event for {event['uuid']}")

    async def _process_input(self, event):
        await db.update_array_append(
            table_name="send_log_details",
            append_data={
                "second_input_time": event["timestamp"],
                "second_input_src": event["ip"],
                "second_input_dev": event["user_agent"],
                "second_input_info": event["data"]
            },
            condition={"uuid": event["uuid"]}
        )
        logger.debug(f"Processed input event for {event['uuid']}")

    async def stop(self):
        self.running = False
        logger.info("PersistenceWorker stopping...")
