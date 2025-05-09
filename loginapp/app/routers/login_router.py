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

# @router.get("/login")
# async def login(request: Request):
#     return templates.TemplateResponse("login.html", {"request": request, "title": "假登入網頁"})

@router.get("/login/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: str): 
    # return templates.TemplateResponse("login.html", {"request": request, "title": "假登入網頁"})
    with open("app/templates/login.html", "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content, media_type="text/html")


# 進入login後記錄id
class VisitData(BaseModel):
    url: str

@router.post("/api/visit")
async def log_visit(data: VisitData, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host)           # 記錄使用者的id資訊
    now = datetime.now().isoformat()   # 記錄當下時間

    # 寫入csv
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now, "visit", data.url, ip, ""])

    return

# 登入後記錄id及email
class LoginData(BaseModel):
    email: str
    url: str

@router.post("/api/login")
async def log_login(data: LoginData, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host)           # 記錄使用者的ip資訊(抓header上的ip)
    now = datetime.now().isoformat()   # 記錄當下時間

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now, "login", data.url, ip, data.email])

    return
