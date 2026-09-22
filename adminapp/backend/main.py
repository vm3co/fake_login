import os
import asyncio
import uuid
from datetime import datetime
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
from backend.repository.models import SendTask, SendLogStats, JobRun, SystemConfig
from sqlalchemy import select, update, delete, or_
from sqlalchemy.sql import func

from backend.services.getSe2data import get_se2_data
from backend.services.db_user import DBUser
from backend.services.get_token import get_token
from backend.services.log_manager import Logger
from backend.services.job_queue import job_queue

# 引入分離的路由模組
from backend.api.data_api import get_router as log_router
from backend.api.user_api import get_router as user_router
from backend.api.trigger_page_api import get_router as page_router
from backend.api import notification_api, job_api, create_task_api, domain_api

from backend.workers.archiving_worker import ArchivingWorker
from backend.repository.database import init_db


# Global worker instances
archiving_worker = ArchivingWorker()

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
        raise

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
        raise

async def check_sendtasks_job():
    """
    定時執行 check_sendtasks 任務
    """
    logger.info("check_sendtasks_job 執行")
    try:
        result = await db_user.sync_sendtasks()
        logger.info(f"check_sendtasks_job 完成 - 新增: {len(result['added'])}, 變更: {len(result['changed'])}, 刪除: {result['deleted']}, 封存: {result['archived']}")
    except Exception as e:
        logger.error(f"check_sendtasks_job 執行失敗: {str(e)}")
        raise

async def nightly_sync_job():
    """每日凌晨統一執行：先同步任務清單，再刷新統計"""
    logger.info("nightly_sync_job 開始")
    try:
        await check_sendtasks_job()      # 步驟1：同步任務清單
        await refresh_sendlog_stats_job() # 步驟2：刷新統計資料
        logger.info("nightly_sync_job 完成")
    except Exception as e:
        logger.error(f"nightly_sync_job 失敗: {e}")
        raise

async def enqueue_scheduler_job(job_code, job_type, execution_class, job_func):
    scheduled_for = datetime.now(tz=ZoneInfo("Asia/Taipei")).replace(second=0, microsecond=0)
    dedupe_key = f"scheduler:{job_code}:{scheduled_for.isoformat()}"
    try:
        await db_controller.create(JobRun, {
            "job_id": str(uuid.uuid4()),
            "source": "scheduler",
            "job_code": job_code,
            "job_type": job_type,
            "display_name": job_type,
            "owner_username": "system",
            "status": "queued",
            "execution_class": execution_class,
            "message": f"系統排程已排隊：{job_type}",
            "scheduled_for": scheduled_for,
            "dedupe_key": dedupe_key,
        })
    except Exception as error:
        if "dedupe" not in str(error).lower() and "unique" not in str(error).lower():
            raise
    job_queue.wake()

def scheduler_enqueue_callback(job_code, job_type, execution_class, job_func):
    async def callback():
        await enqueue_scheduler_job(job_code, job_type, execution_class, job_func)

    return callback

def tracked_scheduler_job(job_type, job_func):
    async def wrapper():
        job_id = str(uuid.uuid4())
        await db_controller.create(JobRun, {
            "job_id": job_id,
            "source": "scheduler",
            "job_type": job_type,
            "owner_username": "system",
            "status": "running",
            "message": f"系統排程執行中：{job_type}",
        })
        try:
            result = await job_func()
            await db_controller.update(JobRun, {"job_id": job_id}, {
                "status": "completed",
                "result": result,
                "finished_at": func.now(),
            })
            return result
        except asyncio.CancelledError:
            await db_controller.update(JobRun, {"job_id": job_id}, {
                "status": "cancelled",
                "finished_at": func.now(),
            })
            raise
        except Exception as error:
            await db_controller.update(JobRun, {"job_id": job_id}, {
                "status": "failed",
                "error": str(error),
                "finished_at": func.now(),
            })
            raise

    return wrapper

SCHEDULER_CONFIG = {
    "scheduler_refresh_token_enabled": "refresh_token",
    "scheduler_refresh_today_create_task_enabled": "refresh_today_create_task",
    "scheduler_refresh_notyet_today_tasks_enabled": "refresh_notyet_today_tasks",
    "scheduler_nightly_sync_enabled": "nightly_sync",
    "scheduler_archiving_enabled": "archiving_job",
}

RUNTIME_CONFIG_KEYS = (*SCHEDULER_CONFIG, "startup_cache_warming_enabled")
RUNTIME_CONFIG_DEFAULTS = {
    key: key == "scheduler_refresh_token_enabled"
    for key in RUNTIME_CONFIG_KEYS
}
SCHEDULE_CONFIG_DEFAULTS = {
    "scheduler_refresh_token_minutes": 10,
    "scheduler_refresh_today_create_task_minutes": 60,
    "scheduler_refresh_notyet_today_tasks_minutes": 30,
    "scheduler_nightly_sync_time": "01:00",
    "scheduler_archiving_time": "02:00",
}

async def load_runtime_config():
    values = {}
    for key in RUNTIME_CONFIG_KEYS:
        record = await db_controller.get_one(SystemConfig, {"config_key": key})
        values[key] = record.config_value == "true" if record else RUNTIME_CONFIG_DEFAULTS[key]
    return values

async def load_schedule_config():
    values = {}
    for key, default in SCHEDULE_CONFIG_DEFAULTS.items():
        record = await db_controller.get_one(SystemConfig, {"config_key": key})
        values[key] = int(record.config_value) if record and key.endswith("_minutes") else (
            record.config_value if record else default
        )
    return values

def parse_daily_time(value):
    hour, minute = value.split(":")
    return int(hour), int(minute)

def start_scheduler(runtime_config, schedule_config):
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Taipei"))  # 重點：設定時區
    logger.info(f"目前排程使用時區：{scheduler.timezone}")

    nightly_hour, nightly_minute = parse_daily_time(schedule_config["scheduler_nightly_sync_time"])
    archiving_hour, archiving_minute = parse_daily_time(schedule_config["scheduler_archiving_time"])

    scheduler.add_job(
        tracked_scheduler_job("更新 SE2 Token", refresh_token_job),
        'interval',
        minutes=schedule_config["scheduler_refresh_token_minutes"],
        id='refresh_token', max_instances=1, coalesce=True, misfire_grace_time=300
    )
    scheduler.add_job(
        scheduler_enqueue_callback(
            "refresh_today_create_task", "更新今日建立任務", "maintenance_exclusive", refresh_today_create_task_job
        ),
        'interval',
        minutes=schedule_config["scheduler_refresh_today_create_task_minutes"],
        id='refresh_today_create_task', max_instances=1, coalesce=True, misfire_grace_time=1800
    )
    scheduler.add_job(
        scheduler_enqueue_callback(
            "refresh_notyet_today_tasks", "刷新今日未完成任務", "scheduler_itemized", refresh_notyet_today_tasks_job
        ),
        'interval',
        minutes=schedule_config["scheduler_refresh_notyet_today_tasks_minutes"],
        id='refresh_notyet_today_tasks', max_instances=1, coalesce=True, misfire_grace_time=900
    )
    scheduler.add_job(
        scheduler_enqueue_callback(
            "nightly_sync", "每日任務清單與統計同步", "maintenance_exclusive", nightly_sync_job
        ),
        'cron',
        hour=nightly_hour,
        minute=nightly_minute,
        id='nightly_sync', max_instances=1, coalesce=True, misfire_grace_time=21600
    )
    scheduler.add_job(
        scheduler_enqueue_callback(
            "archiving_job", "封存逾期任務", "maintenance_exclusive", archiving_worker.start
        ),
        'cron',
        hour=archiving_hour,
        minute=archiving_minute,
        id='archiving_job', max_instances=1, coalesce=True, misfire_grace_time=21600
    )
    scheduler.start()
    for config_key, job_id in SCHEDULER_CONFIG.items():
        if not runtime_config[config_key]:
            scheduler.pause_job(job_id)
    logger.info("APScheduler 啟動")
    logger.info(f"refresh_token_job 已排程在每 {schedule_config['scheduler_refresh_token_minutes']} 分鐘執行")
    logger.info(f"refresh_today_create_task_job 已排程在每 {schedule_config['scheduler_refresh_today_create_task_minutes']} 分鐘執行")
    logger.info(f"refresh_notyet_today_tasks_job 已排程在每 {schedule_config['scheduler_refresh_notyet_today_tasks_minutes']} 分鐘執行")
    logger.info(f"nightly_sync_job 已排程在每日 {schedule_config['scheduler_nightly_sync_time']} 執行")
    logger.info(f"archiving_job 已排程在每日 {schedule_config['scheduler_archiving_time']} 執行")
    return scheduler

# 引入資料庫
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize ORM (Create tables if they don't exist)
    await init_db()
    
    await refresh_token_job()   # 啟動時仍需先取得 Token，開關只控制週期更新
    await db_user.table_initialize()
    logger.info("資料庫初始化完成")
    runtime_config = await load_runtime_config()
    schedule_config = await load_schedule_config()
    job_queue.register("refresh_today_create_task", lambda _job_id: refresh_today_create_task_job())
    job_queue.register("refresh_notyet_today_tasks", lambda _job_id: refresh_notyet_today_tasks_job())
    job_queue.register("nightly_sync", lambda _job_id: nightly_sync_job())
    job_queue.register("archiving_job", lambda _job_id: archiving_worker.start())
    await job_queue.start()

    # Cache Warming logic 移到背景執行，避免阻塞啟動
    async def run_cache_warming():
        try:
            logger.info("Starting Cache Warming in background...")
            # Fetch active tasks (is_archived is False or NULL)
            active_uuids = []
            tasks = await db_controller.get(SendTask, {"is_archived": False})
            active_uuids = [task.sendtask_uuid for task in tasks]

            if active_uuids:
                 await db_user.refresh_sendlog_stats(active_uuids)
                 logger.info(f"Cache Warming completed for {len(active_uuids)} active tasks.")
            else:
                 logger.info("No active tasks found for Cache Warming.")
        except Exception as e:
            logger.error(f"Cache Warming failed: {str(e)}")
            raise

    scheduler = start_scheduler(runtime_config, schedule_config)
    runtime_tasks = {"cache_warming": None}
    runtime_lock = asyncio.Lock()

    def start_runtime_task(name, job_type, job_func):
        task = runtime_tasks.get(name)
        if task and not task.done():
            return task
        task = asyncio.create_task(tracked_scheduler_job(job_type, job_func)())
        runtime_tasks[name] = task
        return task

    def get_runtime_status():
        status = {
            config_key: scheduler.get_job(job_id).next_run_time is not None
            for config_key, job_id in SCHEDULER_CONFIG.items()
        }
        status["startup_cache_warming_enabled"] = runtime_config["startup_cache_warming_enabled"]
        return status

    async def apply_runtime_config(values, new_schedule_config):
        async with runtime_lock:
            previous_cache_warming = runtime_config["startup_cache_warming_enabled"]
            runtime_config.update(values)
            schedule_config.update(new_schedule_config)

            scheduler.reschedule_job(
                "refresh_token",
                trigger="interval",
                minutes=schedule_config["scheduler_refresh_token_minutes"],
            )
            scheduler.reschedule_job(
                "refresh_today_create_task",
                trigger="interval",
                minutes=schedule_config["scheduler_refresh_today_create_task_minutes"],
            )
            scheduler.reschedule_job(
                "refresh_notyet_today_tasks",
                trigger="interval",
                minutes=schedule_config["scheduler_refresh_notyet_today_tasks_minutes"],
            )
            nightly_hour, nightly_minute = parse_daily_time(schedule_config["scheduler_nightly_sync_time"])
            scheduler.reschedule_job(
                "nightly_sync",
                trigger="cron",
                hour=nightly_hour,
                minute=nightly_minute,
            )
            archiving_hour, archiving_minute = parse_daily_time(schedule_config["scheduler_archiving_time"])
            scheduler.reschedule_job(
                "archiving_job",
                trigger="cron",
                hour=archiving_hour,
                minute=archiving_minute,
            )

            for config_key, job_id in SCHEDULER_CONFIG.items():
                if values[config_key]:
                    scheduler.resume_job(job_id)
                else:
                    scheduler.pause_job(job_id)

            cache_task = runtime_tasks.get("cache_warming")
            if not values["startup_cache_warming_enabled"] and cache_task and not cache_task.done():
                cache_task.cancel()
                await asyncio.gather(cache_task, return_exceptions=True)
            elif values["startup_cache_warming_enabled"] and not previous_cache_warming:
                start_runtime_task("cache_warming", "啟動快取預熱", run_cache_warming)

            return get_runtime_status()

    app.state.scheduler = scheduler
    app.state.get_runtime_status = get_runtime_status
    app.state.apply_runtime_config = apply_runtime_config

    if runtime_config["startup_cache_warming_enabled"]:
        start_runtime_task("cache_warming", "啟動快取預熱", run_cache_warming)
    
    yield
    
    # Shutdown
    scheduler.shutdown(wait=False)
    await job_queue.stop()
    for task in runtime_tasks.values():
        if task is None:
            continue
        if not task.done():
            task.cancel()
    await asyncio.gather(
        *(task for task in runtime_tasks.values() if task is not None),
        return_exceptions=True,
    )

app = FastAPI(
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

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
app.include_router(domain_api.router, prefix="/api/domain")

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