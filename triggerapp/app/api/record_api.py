from pydantic import BaseModel
from datetime import datetime
import os
import csv
import json
from app.services.redis_client import RedisClient
from fastapi import Request, APIRouter, Depends
from typing import Dict, Any

from app.repository.db_controller import db
from app.services.log_manager import Logger


logger = Logger().get_logger()

redis_client = RedisClient()

router = APIRouter()

async def get_request_info(request: Request) -> Dict[str, Any]:
    """
    從請求標頭中提取 IP 和 User-Agent。
    """
    ip = request.headers.get("x-forwarded-for", request.client.host)
    user_agent = request.headers.get("User-Agent", "Unknown")  # 取得 User-Agent
    return {"ip": ip, "user_agent": user_agent}

async def writer_db(url_id, columns_list, new_data):
    table_name = url_id[16:48]
    person_uuid = url_id[48:] + url_id[:16]

    # 使用 Atomic Append 更新，無需先讀再寫
    append_data = dict(zip(columns_list, new_data))
    await db.update_array_append(table_name, append_data, {"uuid": person_uuid})

async def writer_test(type, new_data):
    file = 'data/test_visit.csv' if type == 'visit' else 'data/test_input.csv'
    with open(file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 使用 writerow 寫入單行
        writer.writerow(new_data)

# 登入後記錄id及email
class LoginData(BaseModel):
    email: str = None  # Make email optional
    input_data: str = None
    url: str

@router.post("/input")
async def log_input(
    data: LoginData, 
    request_info: Dict = Depends(get_request_info)
    ):
    url_id = data.url.split("/")[-1][:64]
    now = int(datetime.now().timestamp())   # 記錄當下時間戳

    # Determine what info to record: input_data has priority, fallback to email
    info_to_record = data.input_data if data.input_data else data.email
    
    # 建構 Event Data (JSON)
    # Parse UUIDs according to user logic
    if len(url_id) == 64:
        # table_name = url_id[16:48] (sendtask_uuid)
        # person_uuid = url_id[48:] + url_id[:16] (uuid)
        sendtask_uuid = url_id[16:48]
        person_uuid = url_id[48:] + url_id[:16]
    else:
        # Fallback
        sendtask_uuid = None
        person_uuid = url_id

    event_data = {
        "type": "input",
        "uuid": person_uuid,          # 用於 DB 更新
        "sendtask_uuid": sendtask_uuid, # 用於 Cache Invalidation
        "timestamp": now,
        "ip": request_info["ip"],
        "user_agent": request_info["user_agent"],
        "data": info_to_record
    }

    if url_id == "test":
        new_data = [now, request_info["ip"], request_info["user_agent"], info_to_record]
        await writer_test('input', new_data)
    else:
        # 改為寫入 Redis Buffer
        try:
            client = await redis_client.get_client()
            await client.rpush("buffer:trigger_events", json.dumps(event_data))
        except Exception as e:
            logger.error(f"Failed to push input event to Redis: {e}")
            
    return {"status": "success"}
