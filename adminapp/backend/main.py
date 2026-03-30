import os
import asyncio
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.requests import Request
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, SendLogStats
from sqlalchemy import select, update, delete, or_

from backend.services.getSe2data import get_se2_data
from backend.services.db_user import DBUser
from backend.services.get_token import get_token
from backend.services.log_manager import Logger

# 引入分離的路由模組
from backend.api.data_api import get_router as log_router
from backend.api.user_api import get_router as user_router
from backend.api.trigger_page_api import get_router as page_router
from backend.api import notification_api, job_api, create_task_api

from backend.workers.sync_worker import SyncWorker
from backend.workers.archiving_worker import ArchivingWorker
from backend.repository.database import init_db


# Global worker instances
sync_worker = SyncWorker()
archiving_worker = ArchivingWorker()
worker_tasks = []

db_user = DBUser()
logger = Logger().get_logger()

def dict_to_hashable(d):
    return tuple(sorted(
        (k, tuple(v) if isinstance(v, list) else v)
        for k, v in d.items()
    ))

def hashable_to_dict(t):
    return {k: list(v) if isinstance(v, tuple) else v for k, v in t}

# 定義定時任務
async def refresh_token_job():
    # logger.info("refresh_token_job 執行")
    await get_token.refresh()

async def refresh_sendlog_stats_job():
    logger.info("refresh_sendlog_stats_job 執行")
    # 刷新所有 sendlog_stats 資料
    await db_user.refresh_sendlog_stats()

async def refresh_today_create_task_job():
    """
    定時執行 refresh_today_create_task 任務，並更新 sendlog_stats
    """
    logger.info("refresh_today_create_task_job 執行")
    try:
        today_create_tasks_list = await db_user.refresh_today_create_task()
        if today_create_tasks_list:
            refresh_list = []
            # Use DBController.upsert
            refresh_list = [task["sendtask_uuid"] for task in today_create_tasks_list]
            await db_controller.upsert(
                SendTask, 
                today_create_tasks_list, 
                index_elements=['sendtask_uuid']
            )
            
            await db_user.refresh_sendlog_stats(refresh_list)
            logger.info(f"refresh_today_create_task_job 完成 - 新增或更新了 {len(refresh_list)} 個今日任務")
    except Exception as e:
        logger.error(f"refresh_today_create_task_job 執行失敗: {str(e)}")

async def refresh_notyet_today_tasks_job():
    """
    在今天有排程的任務中，刷新那些尚未完成或有失敗的任務
    """
    # logger.info("refresh_notyet_today_tasks_job 執行")
    try:
        # 1. 取得今天有排程的任務 (today_earliest_plan_time != 0)
        #    並選取需要判斷的欄位
        async with db_controller.get_session() as session:
            stmt = select(SendLogStats).where(SendLogStats.today_earliest_plan_time != 0)
            result = await session.execute(stmt)
            tasks_with_today_plan = result.scalars().all()

        if not tasks_with_today_plan:
            # logger.info("refresh_notyet_today_tasks_job: 今日沒有排程中的任務需要檢查。")
            return

        # 2. 篩選出尚未完成 (todayunsend > 0) 或有失敗 (todayfailed > 0) 的任務
        uuids_to_refresh = []
        for task in tasks_with_today_plan:
            # SendLogStats model fields: todayunsend, todayfailed
            if (task.todayunsend and task.todayunsend > 0) or (task.todayfailed and task.todayfailed > 0):
                uuids_to_refresh.append(task.sendtask_uuid)

        if uuids_to_refresh:
            await db_user.refresh_sendlog_stats(uuids_to_refresh)
            logger.info(f"refresh_notyet_today_tasks_job 完成 - 已刷新 {len(uuids_to_refresh)} 個未完成或有失敗的今日任務。")

    except Exception as e:
        logger.error(f"refresh_notyet_today_tasks_job 執行失敗: {str(e)}")

async def check_sendtasks_job():
    """
    定時執行 check_sendtasks 任務
    """
    logger.info("check_sendtasks_job 執行")
    try:
        # 使用和 data_api.py 相同的邏輯
        if request.orgs and request.orgs != ["admin"]:
            sendtasks_columns = None
        
        sendtasks_columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "person_count",
                                "pre_test_end_ut", "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", 
                                "test_end_ut", "test_start_ut", "is_pause", "pre_test_enable", "stop_time_new"]
        
        all_tasksname_list = await db_user.get_se2_sendtasks(column_names=sendtasks_columns)

        tasks = await db_controller.get(SendTask)
        my_tasksname_list = []
        for t in tasks:
            t_dict = {c: getattr(t, c) for c in sendtasks_columns if hasattr(t, c)}
            my_tasksname_list.append(t_dict)

        all_set = set(dict_to_hashable(d) for d in all_tasksname_list)
        my_set = set(dict_to_hashable(d) for d in my_tasksname_list)
        
        added = all_set - my_set
        removed = my_set - all_set

        added_list = [hashable_to_dict(t) for t in added]
        removed_list = [hashable_to_dict(t) for t in removed]

        if added_list:
            refresh_list = [task["sendtask_uuid"] for task in added_list]
            await db_controller.upsert(
                SendTask,
                added_list,
                index_elements=['sendtask_uuid']
            )

            sendlog_stats_status = await db_user.refresh_sendlog_stats(refresh_list)
            logger.info(f"新增了 {len(refresh_list)} 個任務") # simplified count

        del_count = 0
        archive_count = 0
        if removed_list:
            # 確認是否真的已刪除 (404)
            for item in removed_list:
                uuid = item["sendtask_uuid"]
                data = await get_se2_data.get_sendtask(uuid)
                
                if data and data.get("error", {}).get("code") == 404:
                    # sendtasks刪除資料
                    await db_controller.delete(SendTask, {"sendtask_uuid": uuid})
                    # sendlog_stats 刪除資料
                    await db_controller.delete(SendLogStats, {"sendtask_uuid": uuid})
                    del_count += 1
                else:
                    # 僅封存
                    await db_controller.update(SendTask, {"sendtask_uuid": uuid}, {"is_archived": True})
                    archive_count += 1
            
            logger.info(f"刪除 {del_count} 個任務，封存 {archive_count} 個任務")

        logger.info(f"check_sendtasks_job 完成 - 新增: {len(added_list)}, 刪除: {del_count}, 封存: {archive_count}")

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
    # 每60分鐘執行一次，更新今日建立任務
    scheduler.add_job(
        refresh_today_create_task_job,
        'interval',
        minutes=60,
        id='refresh_today_create_task'
    )
    # 每30分鐘執行一次，刷新今日任務
    scheduler.add_job(
        refresh_notyet_today_tasks_job,
        'interval',
        minutes=30,
        id='refresh_notyet_today_tasks'
    )
    # 每天凌晨 0:50 執行 check_sendtasks
    scheduler.add_job(
        check_sendtasks_job,
        'cron',
        hour=0,
        minute=50,
        id='check_sendtasks'
    )
    # 每天凌晨 1:00 執行 sendlog_stats 刷新
    scheduler.add_job(
        refresh_sendlog_stats_job, 
        'cron', 
        hour=1, 
        minute=0,
        id='refresh_sendlog_stats'
    )
    # 每天凌晨 2:00 執行 archiving_worker
    scheduler.add_job(
        archiving_worker.start,
        'cron',
        hour=2,
        minute=0,
        id='archiving_job'
    )
    scheduler.start()
    logger.info("APScheduler 啟動")
    logger.info("refresh_token_job 已排程在每 10 分鐘執行")
    logger.info("refresh_today_create_task_job 已排程在每 60 分鐘執行")
    logger.info("refresh_notyet_today_tasks_job 已排程在每 30 分鐘執行")
    logger.info("check_sendtasks_job 已排程在每日 00:50 執行")
    logger.info("refresh_sendlog_stats_job 已排程在每日 01:00 執行")
    logger.info("archiving_job 已排程在每日 02:00 執行")

# 引入資料庫
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize ORM (Create tables if they don't exist)
    await init_db()
    
    await refresh_token_job()   # 測試初始化 token
    await db_user.table_initialize()
    logger.info("資料庫初始化完成")

    # Cache Warming logic
    try:
        logger.info("Starting Cache Warming...")
        # Fetch active tasks (is_archived is False or NULL)
        active_uuids = []
        stmt = select(SendTask).where(
            or_(SendTask.is_archived == False, SendTask.is_archived.is_(None))
        )
        tasks = await db_controller.execute_scalars(stmt)
        active_uuids = [task.sendtask_uuid for task in tasks]

        if active_uuids:
             await db_user.refresh_sendlog_stats(active_uuids)
             logger.info(f"Cache Warming completed for {len(active_uuids)} active tasks.")
        else:
             logger.info("No active tasks found for Cache Warming.")
    except Exception as e:
        logger.error(f"Cache Warming failed: {e}")
    start_scheduler()  # 啟動 APScheduler

    # Start workers
    sync_worker_work = asyncio.create_task(sync_worker.start())
    worker_tasks.extend([sync_worker_work])
    
    yield
    
    # Shutdown
    await sync_worker_work.stop()
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)

app = FastAPI(lifespan=lifespan)

# 定義允許的來源
origins = [
    "http://localhost",
    "http://localhost:80", # 也可以明確寫上 port
    # 如果未來有其他 domain name 也要加進來
    # "http://your.domain.com",
]

# 將 Middleware 加入到 app
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允許指定的來源
    allow_credentials=True, # 允許 cookies
    allow_methods=["*"],    # 允許所有 HTTP 方法
    allow_headers=["*"],    # 允許所有 HTTP Headers
)

# 註冊路由
app.include_router(log_router(db_user), prefix="/api")
app.include_router(user_router(db_user), prefix="/api")
app.include_router(page_router(db_user), prefix="/api/trigger_page")
app.include_router(notification_api.router, prefix="/api")
app.include_router(job_api.router, prefix="/api")
app.include_router(create_task_api.router, prefix="/api")

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