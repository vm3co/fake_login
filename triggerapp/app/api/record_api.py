from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import os
import csv
from fastapi import Request, APIRouter, Depends
from typing import Dict, Any

from app.core.db_controller import db
from app.services.log_manager import Logger


logger = Logger().get_logger()

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

    # 先取資料
    data = await db.get_db(table_name, person_uuid, columns_list)
    data = data[0]
    logger.debug(f"data: {data}")
    # 寫入資料
    for index, dd in enumerate(data):
        if data[dd] is None: data[dd] = []
        data[dd].append(new_data[index])
    logger.debug(f"data: {data}")
    condition = {"uuid": person_uuid}
    await db.update_db(table_name, data, condition)

async def writer_test(type, new_data):
    file = 'data/test_visit.csv' if type == 'visit' else 'data/test_input.csv'
    with open(file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 使用 writerow 寫入單行
        writer.writerow(new_data)

# 進入login後記錄id
class VisitData(BaseModel):
    url: str

@router.post("/visit")
async def log_visit(
    data: VisitData, 
    request_info: Dict = Depends(get_request_info)
    ):
    url_id = data.url.split("/")[-1]
    now = int(datetime.now().timestamp())   # 記錄當下時間戳
    columns_list = ["second_access_time", "second_access_src", "second_access_dev"]
    new_data = [now, request_info["ip"], request_info["user_agent"]]

    if url_id == "test":
        await writer_test('visit', new_data)
    else:
        # 寫入db
        await writer_db(url_id, columns_list, new_data)

# 登入後記錄id及email
class LoginData(BaseModel):
    email: str
    url: str

@router.post("/input")
async def log_input(
    data: LoginData, 
    request_info: Dict = Depends(get_request_info)
    ):
    url_id = data.url.split("/")[-1][:64]
    now = int(datetime.now().timestamp())   # 記錄當下時間戳
    new_data = [now, request_info["ip"], request_info["user_agent"], data.email]
    columns_list = ["second_input_time", "second_input_src", "second_input_dev", "second_input_info"]

    if url_id == "test":
        await writer_test('input', new_data)
    else:
        # 寫入db
        await writer_db(url_id, columns_list, new_data)
