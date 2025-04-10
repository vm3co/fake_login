from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
# from starlette.middleware.proxy_headers import ProxyHeadersMiddleware


from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import csv
import os

app = FastAPI()
# 獲得真實IP
# app.add_middleware(ProxyHeadersMiddleware)

# 資料儲存到visit_log.csv 同時建立檔案
load_dotenv()  # 會自動讀取 .env 檔案（如果存在於當前目錄或上層）
LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "action", "url", "ip", "email"])

# 掛載靜態文件目錄
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# 設定模板目錄
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "假登入網頁"})

@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "假登入網頁"})



class VisitData(BaseModel):
    url: str

# 進入login後記錄id
@app.post("/api/visit")
async def log_visit(data: VisitData, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host)           # 記錄使用者的id資訊
    # ip = request.client.host           # 記錄使用者的id資訊
    now = datetime.now().isoformat()   # 記錄當下時間

    # 寫入csv
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now, "visit", data.url, ip, ""])

    return

class LoginData(BaseModel):
    email: str
    url: str

# 登入後記錄id及email
@app.post("/api/login")
async def log_login(data: LoginData, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host)           # 記錄使用者的ip資訊(抓header上的ip)
    # ip = request.client.host           # 記錄使用者的id資訊
    now = datetime.now().isoformat()   # 記錄當下時間

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now, "login", data.url, ip, data.email])

    return

def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()