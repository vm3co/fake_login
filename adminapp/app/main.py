import os
from zoneinfo import ZoneInfo
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
from app.services.getSe2data import get_se2_data
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
    # 刷新所有 sendlog_stats 資料
    await db_user.refresh_sendlog_stats()

async def check_sendtasks_job():
    """
    定時執行 check_sendtasks 任務
    """
    logger.info("check_sendtasks_job 執行")
    try:
        # 使用和 data_api.py 相同的邏輯
        sendtasks_columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "pre_test_end_ut",
                             "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", "test_end_ut", 
                             "test_start_ut", "is_pause", "stop_time_new"]
        all_tasksname_list = await db_user.get_se2_sendtasks(sendtasks_columns)

        my_tasksname_list = await db.get_db("sendtasks", column_names=sendtasks_columns)

        def dict_to_hashable(d):
            return tuple(sorted(
                (k, tuple(v) if isinstance(v, list) else v)
                for k, v in d.items()
            ))

        def hashable_to_dict(t):
            return {k: list(v) if isinstance(v, tuple) else v for k, v in t}

        all_set = set(dict_to_hashable(d) for d in all_tasksname_list)
        my_set = set(dict_to_hashable(d) for d in my_tasksname_list)
        
        added = all_set - my_set
        removed = my_set - all_set

        added_list = [hashable_to_dict(t) for t in added]
        removed_list = [hashable_to_dict(t) for t in removed]

        if added_list:
            refresh_list = []
            for task in added_list:
                status = await db.upsert_db(
                    table_name="sendtasks", 
                    data=task, 
                    conflict_keys=["sendtask_uuid"])
                if status == "changed":
                    refresh_list.append(task["sendtask_uuid"])
            sendlog_stats_status = await db_user.refresh_sendlog_stats(refresh_list)

            logger.info(f"新增了 {len(sendlog_stats_status)} 個任務")

        if removed_list:
            for item in removed_list:
                await db.update_db(
                    table_name="sendtasks",
                    data={"is_active": False},
                    condition={"sendtask_uuid": item["sendtask_uuid"]}
                )
            logger.info(f"停用了 {len(removed_list)} 個任務")

        logger.info(f"check_sendtasks_job 完成 - 新增: {len(added_list)}, 停用: {len(removed_list)}")
        
    except Exception as e:
        logger.error(f"check_sendtasks_job 執行失敗: {str(e)}")

def start_scheduler():
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Taipei"))  # 重點：設定時區
    logger.info(f"目前排程使用時區：{scheduler.timezone}")

    # 每10分鐘執行一次
    scheduler.add_job(
        refresh_token_job, 
        'interval', 
        minutes=10,
        id='refresh_token'
    )
    # 每天凌晨 1:00 執行 sendlog_stats 刷新
    scheduler.add_job(
        refresh_sendlog_stats_job, 
        'cron', 
        hour=1, 
        minute=0,
        id='refresh_sendlog_stats'
    )
    # 每天凌晨 1:05 執行 check_sendtasks
    scheduler.add_job(
        check_sendtasks_job, 
        'cron', 
        hour=1, 
        minute=5,
        id='check_sendtasks'
    )
    scheduler.start()
    logger.info("APScheduler 啟動")
    logger.info("refresh_token_job 已排程在每 10 分鐘執行")
    logger.info("refresh_sendlog_stats_job 已排程在每日 01:00 執行")
    logger.info("check_sendtasks_job 已排程在每日 01:05 執行")

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

# 註冊路由
app.include_router(log_router(db, db_user), prefix="/api")
app.include_router(user_router(db, db_user), prefix="/api")

# 設定模板目錄：掛載 React 打包好的靜態檔案（注意路徑）
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

from fastapi.responses import JSONResponse  # 新增匯入

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    # 如果是 API 路由，保留原本錯誤
    if request.url.path.startswith("/api"):
        return JSONResponse(content={"detail": "Not Found"}, status_code=404)  # 修改為 JSONResponse
    
    # 如果是前端頁面，回傳 index.html 給 React Router 處理
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, status_code=status.HTTP_200_OK)
    
    # 沒有 index.html 的話，保留 404
    return JSONResponse(content={"detail": "Not Found"}, status_code=404)  # 修改為 JSONResponse


def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()