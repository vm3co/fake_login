from pydantic import BaseModel
from datetime import datetime
from urllib.parse import urlparse
import os
import csv
import json
from pathlib import Path
from app.services.redis_client import RedisClient
from fastapi import Request, APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from app.services.log_manager import Logger
from app.services.structured_submission import (
    StructuredSubmissionError,
    parse_trigger_url,
    validate_submission,
)
from app.repository.db_controller import db_controller
from app.repository.models import TriggerPage


logger = Logger().get_logger()

redis_client = RedisClient()

router = APIRouter()

async def get_request_info(request: Request) -> Dict[str, Any]:
    """
    從請求標頭中提取 IP 和 User-Agent。
    """
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host
    user_agent = request.headers.get("User-Agent", "Unknown")  # 取得 User-Agent
    return {"ip": ip, "user_agent": user_agent}



async def writer_test(type, new_data):
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    file = data_dir / ('test_visit.csv' if type == 'visit' else 'test_input.csv')
    with open(file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 使用 writerow 寫入單行
        writer.writerow(new_data)

# 登入後記錄id及email
class LoginData(BaseModel):
    email: str = None  # Make email optional
    input_data: str = None
    url: str


class StructuredFieldValue(BaseModel):
    id: str
    value: str


class StructuredInputData(BaseModel):
    url: str
    revision: int
    fields: List[StructuredFieldValue]


def _event_identity(project_id: str) -> tuple[str, str]:
    if len(project_id) == 64:
        return project_id[16:48], project_id[48:] + project_id[:16]
    return None, project_id


async def _store_input_event(project_id: str, info_to_record: str, request_info: Dict):
    now = int(datetime.now().timestamp())
    sendtask_uuid, person_uuid = _event_identity(project_id)
    event_data = {
        "type": "input",
        "uuid": person_uuid,
        "sendtask_uuid": sendtask_uuid,
        "timestamp": now,
        "ip": request_info["ip"],
        "user_agent": request_info["user_agent"],
        "data": info_to_record,
    }

    if project_id in ("test", "99999_99999"):
        await writer_test('input', [now, request_info["ip"], request_info["user_agent"], info_to_record])
        return

    try:
        client = await redis_client.get_client()
        await client.rpush("buffer:trigger_events", json.dumps(event_data))
    except Exception as exc:
        logger.error(f"Failed to push input event to Redis: {exc}")

@router.post("/input")
async def log_input(
    data: LoginData, 
    request_info: Dict = Depends(get_request_info)
    ):
    url_id = urlparse(data.url).path.rstrip("/").split("/")[-1][:64]
    # Determine what info to record: input_data has priority, fallback to email
    info_to_record = data.input_data if data.input_data else data.email
    await _store_input_event(url_id, info_to_record, request_info)
    return {"status": "success"}


@router.post("/structured-input")
async def log_structured_input(
    data: StructuredInputData,
    request_info: Dict = Depends(get_request_info),
):
    try:
        page_value, project_id = parse_trigger_url(data.url)
    except StructuredSubmissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    page = await db_controller.get_one(TriggerPage, {"page_value": page_value})
    if not page or page.page_spec is None:
        raise HTTPException(status_code=404, detail="找不到結構化頁面")

    try:
        info_to_record = validate_submission(
            page.page_spec,
            data.revision,
            [field.model_dump() for field in data.fields],
            page.spec_revision,
        )
    except StructuredSubmissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    await _store_input_event(project_id, info_to_record, request_info)
    return {"status": "success"}
