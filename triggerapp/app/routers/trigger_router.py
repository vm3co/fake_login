from pydantic import BaseModel
from datetime import datetime
import csv
import os
from pathlib import Path
from fastapi import FastAPI, Request, APIRouter, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response


BASE_DIR = Path(__file__).resolve().parent.parent

router = APIRouter()

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


@router.get("/page/{page_name}/{project_id}", response_class=HTMLResponse)
async def project_detail_dynamic(request: Request, page_name: str, project_id: str):
    
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
