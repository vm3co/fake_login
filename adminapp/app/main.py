from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import csv
import os


app = FastAPI()

# 開啟後台資料visit_log.csv
load_dotenv()  # 會自動讀取 .env 檔案（如果存在於當前目錄或上層）
LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")

# 掛載靜態文件目錄
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# 設定模板目錄
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def index(request: Request):
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = [row for row in reader]

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "data": data,
        "title": "後臺資料"
    })

def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()