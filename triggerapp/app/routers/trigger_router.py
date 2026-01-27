from pydantic import BaseModel
from datetime import datetime
import csv
import os
import json
from app.services.redis_client import RedisClient
from pathlib import Path
from typing import Dict, Any
from fastapi import FastAPI, Request, APIRouter, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from app.repository.db_controller import db
from app.services.log_manager import Logger


redis_client = RedisClient()

BASE_DIR = Path(__file__).resolve().parent.parent

logger = Logger().get_logger()

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

async def writer_db(url_id, columns_list, new_data):
    if len(url_id) < 48:
        # Avoid empty table name error for test/short IDs
        return
        
    table_name = url_id[16:48]
    person_uuid = url_id[48:] + url_id[:16]

    # 使用 Atomic Append 更新，無需先讀再寫
    append_data = dict(zip(columns_list, new_data))
    await db.update_array_append(table_name, append_data, {"uuid": person_uuid})

# 設定模板目錄
templates_dir = BASE_DIR / "templates"
templates = Jinja2Templates(directory=templates_dir)

@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "假登入網頁"})

@router.get("/warning")
async def warning_page(request: Request):
    # 這裡會去 templates 資料夾找 warning.html
    return templates.TemplateResponse("warning.html", {"request": request, "title": "社交工程演練警告"})



async def _shared_project_detail(request: Request, page_name: str, project_id: str, url: str, event_type: str):
    # 統一先進行紀錄
    request_info = await get_request_info(request)
    now = int(datetime.now().timestamp())
    
    # Parse UUIDs according to user logic
    if len(project_id) == 64:
        # table_name = project_id[16:48] (sendtask_uuid)
        # person_uuid = project_id[48:] + project_id[:16] (uuid)
        sendtask_uuid = project_id[16:48]
        person_uuid = project_id[48:] + project_id[:16]
    else:
        # Fallback for old or test IDs
        sendtask_uuid = None
        person_uuid = project_id

    event_data = {
        "type": event_type,
        "uuid": person_uuid,          # 用於 DB 更新 condition (primary key)
        "sendtask_uuid": sendtask_uuid, # 用於 Cache Invalidation
        "timestamp": now,
        "ip": request_info["ip"],
        "user_agent": request_info["user_agent"]
    }
    
    new_data = [now, request_info["ip"], request_info["user_agent"]]
    
    if project_id == "test" or project_id == "99999_99999":
        # Ensure data directory exists
        data_file = Path('data/test_visit.csv')
        data_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(data_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 使用 writerow 寫入單行
            writer.writerow(new_data)
    else:   
        # 寫入 Redis Buffer
        try:
            client = await redis_client.get_client()
            await client.rpush("buffer:trigger_events", json.dumps(event_data))
        except Exception as e:
            logger.error(f"Failed to push {event_type} event to Redis: {e}")

    # 判斷是 from-url (轉址) 還是 一般頁面 (顯示模板)
    if page_name == "from-url":
        if not url:
             # 如果沒有提供 url 參數，可以導向一個預設頁面或報錯，這裡暫時導回首頁或顯示錯誤
             return Response("Missing 'url' parameter for redirection.", status_code=400)
        return RedirectResponse(url, status_code=307)

    # 根據 URL 的 page_name 組合出模板檔案名稱
    template_name = f"{page_name}.html"
    
    # 檢查這個 HTML 檔案是否存在於 templates 資料夾中
    template_path = templates_dir / template_name
    
    if not template_path.is_file():
        # 如果檔案不存在，就回傳 404 錯誤
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found.")
    
    # 檔案存在，組合 context
    context = {
        "request": request,
        "title": f"{page_name.capitalize()} 登入頁面",
        "project_id": project_id,
        "api_base_path": request.scope.get("root_path", "")
    }
    
    # 4. 回傳對應的模板
    return templates.TemplateResponse(template_name, context)

@router.get("/page/{page_name}/{project_id}", response_class=HTMLResponse)
async def project_detail_dynamic(request: Request, page_name: str, project_id: str, url: str = None):
    return await _shared_project_detail(request, page_name, project_id, url, "visit")

@router.get("/qr/{page_name}/{project_id}", response_class=HTMLResponse)
async def qr_project_detail_dynamic(request: Request, page_name: str, project_id: str, url: str = None):
    return await _shared_project_detail(request, page_name, project_id, url, "qr_visit")
