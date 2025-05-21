from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import os
from fastapi import Request, APIRouter

from app.core.db_controller import db
from app.services.log_manager import Logger


logger = Logger().get_logger()

LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")
router = APIRouter()

async def writer_db(url_id, new_data):
    table_name = url_id[16:48]
    person_uuid = url_id[48:] + url_id[:16]

    # 先取資料
    column_names = ["access_active", "access_ip", "access_time"]
    data = await db.get_db(table_name, person_uuid, column_names)
    data = data[0]
    logger.debug(f"data: {data}")
    # 寫入資料
    for index, dd in enumerate(data):
        if data[dd] is None: data[dd] = []
        data[dd].append(new_data[index])
        logger.debug(f"{index}: {data[dd]}")
    logger.debug(f"data: {data}")
    condition = {"uuid": person_uuid}
    logger.debug(f"uuid: {person_uuid}")
    await db.update_db(table_name, data, condition)

# 進入login後記錄id
class VisitData(BaseModel):
    url: str

@router.post("/visit")
async def log_visit(data: VisitData, request: Request):
    url_id = data.url.split("/")[-1]
    ip = request.headers.get("x-forwarded-for", request.client.host)           # 記錄使用者的id資訊
    now = int(datetime.now().timestamp())   # 記錄當下時間戳
    new_data = ["visit", ip, now]

    # 寫入db
    await writer_db(url_id, new_data)

# 登入後記錄id及email
class LoginData(BaseModel):
    email: str
    url: str

@router.post("/login")
async def log_login(data: LoginData, request: Request):
    url_id = data.url.split("/")[-1]
    ip = request.headers.get("x-forwarded-for", request.client.host)           # 記錄使用者的ip資訊(抓header上的ip)
    now = int(datetime.now().timestamp())   # 記錄當下時間戳
    new_data = [f"login:{data.email}", ip, now]

    # 寫入db
    await writer_db(url_id, new_data)
