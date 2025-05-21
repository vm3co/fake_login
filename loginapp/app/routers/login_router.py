from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import csv
import os
from fastapi import FastAPI, Request, APIRouter
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response

LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")
router = APIRouter()

# 設定模板目錄
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "假登入網頁"})

@router.get("/login/test/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str): 
    with open("app/templates/login_test.html", "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content, media_type="text/html")

@router.get("/login/googledrive/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str): 
    with open("app/templates/login_googledrive.html", "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content, media_type="text/html")
