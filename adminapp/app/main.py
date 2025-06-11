import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.requests import Request
from fastapi import status
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio


from app.core.db_controller import ApplianceDB
from app.services.db_user import DBUser
from app.services.get_token import get_token
from app.services.log_manager import Logger


# 引入分離的路由模組
from frontend.src.api.data_api import get_router as log_router
from frontend.src.api.user_api import get_router as user_router


db = ApplianceDB()
db_user = DBUser(db=db)
logger = Logger().get_logger()

# 定義定時任務
async def refresh_token_job():
    logger.info("refresh_token_job 執行")
    await get_token.refresh()

async def refresh_sendlog_stats_job():
    logger.info("refresh_sendlog_stats_job 執行")
    # 刷新 sendlog_stats 資料
    await db_user.refresh_sendlog_stats()

def start_scheduler():
    scheduler = AsyncIOScheduler()
    # 每10分鐘執行一次
    scheduler.add_job(refresh_token_job, 'interval', minutes=10)
    scheduler.add_job(refresh_sendlog_stats_job, 'interval', minutes=10)
    scheduler.start()
    logger.info("APScheduler 啟動")

# 引入資料庫
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.db_init()
    await refresh_token_job()   # 測試初始化 token
    await db_user.table_initialize()
    logger.info("資料庫初始化完成")
    start_scheduler()  # 啟動 APScheduler
    yield
    await db.db_close()

app = FastAPI(lifespan=lifespan)
# app = FastAPI()

# 開啟後台資料visit_log.csv
load_dotenv()  # 會自動讀取 .env 檔案（如果存在於當前目錄或上層）
LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")

# 註冊路由
app.include_router(log_router(db, db_user), prefix="/api")
app.include_router(user_router(db, db_user), prefix="/api")

# 設定模板目錄：掛載 React 打包好的靜態檔案（注意路徑）
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    # 如果是 API 路由，保留原本錯誤
    if request.url.path.startswith("/api"):
        return {"detail": "Not Found"}
    
    # 如果是前端頁面，回傳 index.html 給 React Router 處理
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, status_code=status.HTTP_200_OK)
    
    # 沒有 index.html 的話，保留 404
    return {"detail": "Not Found"}


def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()