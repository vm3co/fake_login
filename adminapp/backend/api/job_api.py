from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from backend.services.job_manager import JobManager
from backend.api.user_api import get_current_user
from backend.services.db_user import DBUser
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, Mtmpl, Notification, SendLogStats, JobRun
from sqlalchemy import and_, or_, select
from backend.api.data_api import filter_tasks_by_scope, get_sendtask_scope
from backend.services.log_manager import Logger

logger = Logger().get_logger()
router = APIRouter(
    prefix="/jobs",
    tags=["jobs"]
)

job_manager = JobManager()
# db = ApplianceDB() # Removed
db_user = DBUser()

class JobRequest(BaseModel):
    job_type: str
    params: Dict[str, Any] = {}

def serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def serialize_job_run(job: JobRun) -> Dict[str, Any]:
    return {
        "job_id": job.job_id,
        "source": job.source,
        "type": job.job_type,
        "owner_username": job.owner_username,
        "status": job.status,
        "message": job.message,
        "result": job.result,
        "error": job.error,
        "start_time": serialize_datetime(job.started_at),
        "finished_at": serialize_datetime(job.finished_at),
    }

@router.get("")
async def list_jobs(source: str = "manual", current_user: dict = Depends(get_current_user)):
    if source not in {"manual", "scheduler"}:
        raise HTTPException(status_code=400, detail="Unknown job source")

    filters = [JobRun.source == source]
    if source == "manual" and current_user.get("admin_role") is not True:
        filters.append(JobRun.owner_username == current_user.get("username"))
    if source == "scheduler":
        filters.append(or_(
            JobRun.job_type != "更新 SE2 Token",
            and_(JobRun.job_type == "更新 SE2 Token", JobRun.status == "failed"),
        ))

    running_stmt = (
        select(JobRun)
        .where(*filters, JobRun.status.in_(["pending", "running"]))
        .order_by(JobRun.started_at.desc())
    )
    history_stmt = (
        select(JobRun)
        .where(*filters, JobRun.status.notin_(["pending", "running"]))
        .order_by(JobRun.started_at.desc())
        .limit(100)
    )
    running = await db_controller.execute_scalars(running_stmt)
    history = await db_controller.execute_scalars(history_stmt)
    jobs = sorted(
        [*running, *history],
        key=lambda job: job.started_at,
        reverse=True,
    )
    return [serialize_job_run(job) for job in jobs]

@router.get("/current")
async def get_current_job(current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    job = job_manager.get_current_job(username)
    if job:
        return {
            "job_id": job['job_id'],
            "type": job['type'],
            "status": job['status'],
            "start_time": job['start_time'],
            "message": job.get('message'),
            "result": job.get('result'),
            "error": job.get('error')
        }
    return None

@router.post("/cancel")
async def cancel_job(current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    success = await job_manager.cancel_job(username)
    return {"status": "success", "cancelled": success}

@router.post("/start")
async def start_job(request: JobRequest, current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    job_type = request.job_type
    params = request.params
    
    try:
        if job_type == "refresh_today_create_task":
            orgs = get_sendtask_scope(current_user)
            # Logic from refresh_today_create_task
            async def task_func():
                today_create_task_list = await db_user.refresh_today_create_task()
                today_create_task_list = filter_tasks_by_scope(today_create_task_list, orgs)
                
                if not today_create_task_list:
                    return {"message": "無今日建立任務"}

                refresh_list = [task["sendtask_uuid"] for task in today_create_task_list]
                
                # Batch upsert sendtasks
                await db_controller.upsert(
                    model=SendTask,
                    data_list=today_create_task_list,
                    index_elements=['sendtask_uuid']
                )

                # Also refresh stats
                await db_user.refresh_sendlog_stats(refresh_list)
                
                # Add notification
                details_msg = "更新任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in today_create_task_list])
                
                await db_controller.create(Notification, {
                    "username": username,
                    "title": "檢查今日建立任務完成",
                    "subtitle": f"已更新 {len(refresh_list)} 筆任務",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "check_circle",
                    "icon_color": "success",
                    "details": details_msg
                })

                return {"updated_count": len(refresh_list)}

            await job_manager.start_job(username, "檢查今日建立任務", task_func)

        elif job_type == "update_mtmpl":
            async def task_func():
                # 1. 從 SE2 全量 upsert（含所有 model 欄位）
                result = await db_user.refresh_mtmpl()
                upserted = result.get("upserted", 0)
                if upserted == 0:
                    raise Exception("從 SE2 獲取郵件樣板失敗")

                # 2. 找出本地已不在 SE2 的樣板並刪除
                se2_mtmpl_list = await db_user.get_se2_mtmpl()
                se2_uuids = {item["mtmpl_uuid"] for item in se2_mtmpl_list}

                local_rows = await db_controller.get(Mtmpl)
                removed_count = 0
                for row in local_rows:
                    if row.mtmpl_uuid not in se2_uuids:
                        await db_controller.delete(Mtmpl, {"mtmpl_uuid": row.mtmpl_uuid})
                        removed_count += 1
                        logger.info(f"Removed mtmpl {row.mtmpl_uuid}")

                details_msg = f"更新/新增: {upserted} 筆\n刪除: {removed_count} 筆"

                await db_controller.create(Notification, {
                    "username": username,
                    "title": "更新郵件樣板完成",
                    "subtitle": "同步完成",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "list_alt",
                    "icon_color": "info",
                    "details": details_msg
                })

                return {"upserted": upserted, "removed": removed_count}

            await job_manager.start_job(username, "更新郵件樣板列表", task_func)

        elif job_type == "check_sendtasks":
            orgs = get_sendtask_scope(current_user)
            # Logic from check_sendtasks
            async def task_func():
                result = await db_user.sync_sendtasks(orgs=orgs)

                # 只對新增的 uuid 刷 sendlog_stats（原本邏輯）；跳過重複的 SendTask sync
                added_uuids = [t["sendtask_uuid"] for t in result["added"]]
                if added_uuids:
                    await db_user.refresh_sendlog_stats(
                        added_uuids,
                        ignore_archived=True,
                        skip_sendtask_sync=True,
                    )

                added_cnt = len(result["added"])
                changed_cnt = len(result["changed"])
                details_msg = ""
                if result["added"]:
                    details_msg += "● 新增任務:\n" + "\n".join(t.get("sendtask_id", "Unknown") for t in result["added"]) + "\n"
                if result["changed"]:
                    details_msg += "● 內容更新任務:\n" + "\n".join(t.get("sendtask_id", "Unknown") for t in result["changed"]) + "\n"

                await db_controller.create(Notification, {
                    "username": username,
                    "title": "任務列表更新完成",
                    "subtitle": f"新增 {added_cnt}，更新 {changed_cnt}，刪除 {result['deleted']}，封存 {result['archived']}",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "sync",
                    "icon_color": "info",
                    "details": details_msg,
                })
                return result

            await job_manager.start_job(username, "更新任務列表", task_func)

        elif job_type == "refresh_sendlog_stats":
            orgs = get_sendtask_scope(current_user)
            # Logic from refresh_sendlog_stats
            async def task_func():
                uuids = params.get("uuids", [])
                ignore_archived = params.get("ignore_archived", False)
                if not uuids:
                    return {"message": "未指定任務 UUID"}

                tasks = await db_controller.get(SendTask, filters={"sendtask_uuid": uuids})
                if orgs is not None:
                    tasks = filter_tasks_by_scope(tasks, orgs)
                    uuids = [task.sendtask_uuid for task in tasks]
                    if not uuids:
                        raise HTTPException(status_code=403, detail="無權存取指定任務")

                task_names = {task.sendtask_uuid: task.sendtask_id for task in tasks}
                requested_uuids = list(uuids)
                statuses = await db_user.refresh_sendlog_stats(
                    requested_uuids,
                    ignore_archived=ignore_archived,
                )
                successful_tasks = []
                skipped_tasks = []
                failed_tasks = []

                for task_uuid in requested_uuids:
                    task = {
                        "sendtask_uuid": task_uuid,
                        "sendtask_id": task_names.get(task_uuid, "Unknown"),
                    }
                    status = statuses.get(task_uuid)
                    if status in {"updated", "unchanged"}:
                        successful_tasks.append(task)
                    elif status in {"deleted", "archived"}:
                        skipped_tasks.append({**task, "reason": status})
                    else:
                        failed_tasks.append({**task, "reason": status or "not_found"})

                result = {
                    "updated_count": len(successful_tasks),
                    "successful_tasks": successful_tasks,
                    "skipped_count": len(skipped_tasks),
                    "skipped_tasks": skipped_tasks,
                    "failed_count": len(failed_tasks),
                    "failed_tasks": failed_tasks,
                }
                if failed_tasks and successful_tasks:
                    result["job_status"] = "partial"
                elif failed_tasks:
                    result["job_status"] = "failed"
                    result["error_summary"] = "更新失敗：" + "、".join(
                        task["sendtask_id"] for task in failed_tasks
                    )

                details = []
                if successful_tasks:
                    details.append("● 已更新任務:\n" + "\n".join(task["sendtask_id"] for task in successful_tasks))
                if skipped_tasks:
                    details.append("● 跳過任務:\n" + "\n".join(task["sendtask_id"] for task in skipped_tasks))
                if failed_tasks:
                    details.append("● 更新失敗任務:\n" + "\n".join(task["sendtask_id"] for task in failed_tasks))

                if result.get("job_status") == "failed":
                    title = "任務更新失敗"
                    icon_color = "error"
                elif result.get("job_status") == "partial":
                    title = "任務部分更新完成"
                    icon_color = "warning"
                else:
                    title = "任務更新完成"
                    icon_color = "primary"
                await db_controller.create(Notification, {
                    "username": username,
                    "title": title,
                    "subtitle": f"已更新 {len(successful_tasks)} 筆，跳過 {len(skipped_tasks)} 筆，失敗 {len(failed_tasks)} 筆",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "update",
                    "icon_color": icon_color,
                    "details": "\n\n".join(details),
                })
                return result

            await job_manager.start_job(username, "更新任務統計", task_func)
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown job type: {job_type}")

        return {"status": "success", "message": "任務已開始"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start job {job_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
