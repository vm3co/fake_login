from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from backend.services.job_manager import JobManager
from backend.api.user_api import get_current_user
from backend.services.db_user import DBUser
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, Mtmpl, Notification, SendLogStats, JobRun, JobRunItem
from sqlalchemy import and_, or_, select
from backend.api.data_api import filter_tasks_by_scope, get_sendtask_scope
from backend.services.log_manager import Logger
from backend.services.job_queue import job_queue

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
        "job_code": job.job_code,
        "type": job.job_type,
        "display_name": job.display_name or job.job_type,
        "owner_username": job.owner_username,
        "status": job.status,
        "execution_class": job.execution_class,
        "queue_position": job.queue_sequence,
        "cancel_requested_at": serialize_datetime(job.cancel_requested_at),
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
        .where(*filters, JobRun.status.in_(["queued", "claiming", "running", "cancel_requested"]))
        .order_by(JobRun.started_at.desc())
    )
    history_stmt = (
        select(JobRun)
        .where(*filters, JobRun.status.notin_(["queued", "claiming", "running", "cancel_requested"]))
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
    job_items = await db_controller.get(
        JobRunItem,
        filters={"job_id": [job.job_id for job in jobs]},
    ) if jobs else []
    items_by_job = {}
    for item in job_items:
        items_by_job.setdefault(item.job_id, []).append({
            "sendtask_uuid": item.sendtask_uuid,
            "sendtask_id": item.sendtask_id,
            "status": item.status,
            "reason": item.reason,
        })
    exclusive_jobs = [
        job for job in jobs
        if job.execution_class == "maintenance_exclusive"
        and job.status in {"queued", "claiming", "running", "cancel_requested"}
    ]
    response = []
    for job in jobs:
        blocked_by = next(
            (
                exclusive.display_name or exclusive.job_type
                for exclusive in exclusive_jobs
                if exclusive.queue_sequence < job.queue_sequence
                or exclusive.status in {"claiming", "running", "cancel_requested"}
            ),
            None,
        ) if job.execution_class == "manual_shared" and job.status == "queued" else None
        response.append({
            **serialize_job_run(job),
            "blocked_by_display_name": blocked_by,
            "items": items_by_job.get(job.job_id, []),
        })
    return response

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    job = await db_controller.get_one(JobRun, {"job_id": job_id, "source": "manual"})
    if not job or job.owner_username != username:
        raise HTTPException(status_code=404, detail="找不到可取消的任務")
    if job.status not in {"queued", "claiming", "running", "cancel_requested"}:
        raise HTTPException(status_code=409, detail="任務已結束，無法取消")
    result = await job_queue.cancel(username, job_id)
    if result == "finished":
        raise HTTPException(status_code=409, detail="任務已結束，無法取消")
    if result == "not_found":
        raise HTTPException(status_code=404, detail="找不到可取消的任務")
    return {"status": "success", "cancelled": True}

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
                
                return {"updated_count": len(refresh_list)}

            admission = await job_manager.start_job(username, "檢查今日建立任務", task_func, job_code=job_type)

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

                return {"upserted": upserted, "removed": removed_count}

            admission = await job_manager.start_job(username, "更新郵件樣板列表", task_func, job_code=job_type)

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
                return result

            admission = await job_manager.start_job(username, "更新任務列表", task_func, job_code=job_type)

        elif job_type == "refresh_sendlog_stats":
            orgs = get_sendtask_scope(current_user)
            # Logic from refresh_sendlog_stats
            requested_uuids = params.get("uuids", [])
            if not requested_uuids:
                raise HTTPException(status_code=400, detail="未指定任務 UUID")
            tasks = await db_controller.get(SendTask, filters={"sendtask_uuid": requested_uuids})
            if orgs is not None:
                tasks = filter_tasks_by_scope(tasks, orgs)
            items = [
                {"sendtask_uuid": task.sendtask_uuid, "sendtask_id": task.sendtask_id}
                for task in tasks
            ]
            if not items:
                raise HTTPException(status_code=403, detail="無權存取指定任務")

            async def task_func(*, accepted_items, job_id):
                uuids = [item["sendtask_uuid"] for item in accepted_items]
                ignore_archived = params.get("ignore_archived", False)
                task_names = {item["sendtask_uuid"]: item["sendtask_id"] for item in accepted_items}
                statuses = {}
                for item in accepted_items:
                    task_uuid = item["sendtask_uuid"]
                    await job_manager.mark_item(job_id, task_uuid, "running")
                    try:
                        result = await db_user.refresh_sendlog_stats([task_uuid], ignore_archived=ignore_archived)
                        statuses[task_uuid] = result.get(task_uuid, "error")
                    except Exception as error:
                        logger.error(f"Failed to refresh task {task_uuid}: {error}")
                        statuses[task_uuid] = "error"
                successful_tasks = []
                skipped_tasks = []
                failed_tasks = []

                for task_uuid in uuids:
                    task = {
                        "sendtask_uuid": task_uuid,
                        "sendtask_id": task_names.get(task_uuid, "Unknown"),
                    }
                    status = statuses.get(task_uuid)
                    if status in {"updated", "unchanged"}:
                        successful_tasks.append(task)
                        await job_manager.mark_item(job_id, task_uuid, "completed")
                    elif status in {"deleted", "archived"}:
                        skipped_tasks.append({**task, "reason": status})
                        await job_manager.mark_item(job_id, task_uuid, "skipped", status)
                    else:
                        failed_tasks.append({**task, "reason": status or "not_found"})
                        await job_manager.mark_item(job_id, task_uuid, "failed", status or "not_found")

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

                return result

            admission = await job_manager.start_job(
                username,
                "更新任務統計",
                task_func,
                job_code=job_type,
                items=items,
                request_params={"ignore_archived": params.get("ignore_archived", False)},
            )

        elif job_type == "upsert_selected_sendtasks":
            requested_uuids = params.get("uuids", [])
            if not requested_uuids:
                raise HTTPException(status_code=400, detail="未指定任務 UUID")

            orgs = get_sendtask_scope(current_user)
            items = []
            for task_uuid in dict.fromkeys(requested_uuids):
                record = await db_user._build_sendtask_record_from_detail(task_uuid)
                if not record:
                    continue
                if orgs is not None and not filter_tasks_by_scope([record], orgs):
                    continue
                items.append({
                    "sendtask_uuid": task_uuid,
                    "sendtask_id": record.get("sendtask_id", "Unknown"),
                })
            if not items:
                raise HTTPException(status_code=403, detail="無權存取指定任務或任務已不存在")

            async def task_func(*, accepted_items, job_id):
                successful_tasks = []
                failed_tasks = []
                for item in accepted_items:
                    task_uuid = item["sendtask_uuid"]
                    await job_manager.mark_item(job_id, task_uuid, "running")
                    try:
                        result = await db_user.upsert_sendtasks_by_uuids([task_uuid])
                        if not result["upserted"]:
                            raise RuntimeError("任務不存在或無法取得最新資料")
                        stats = await db_user.refresh_sendlog_stats(
                            [task_uuid],
                            ignore_archived=True,
                        )
                        status = stats.get(task_uuid, "error")
                        if status in {"updated", "unchanged"}:
                            successful_tasks.append(item)
                            await job_manager.mark_item(job_id, task_uuid, "completed")
                        else:
                            failed_tasks.append({**item, "reason": status})
                            await job_manager.mark_item(job_id, task_uuid, "failed", status)
                    except Exception as error:
                        logger.error(f"Failed to update selected task {task_uuid}: {error}")
                        failed_tasks.append({**item, "reason": str(error)})
                        await job_manager.mark_item(job_id, task_uuid, "failed", str(error))

                result = {
                    "updated_count": len(successful_tasks),
                    "successful_tasks": successful_tasks,
                    "skipped_count": 0,
                    "skipped_tasks": [],
                    "failed_count": len(failed_tasks),
                    "failed_tasks": failed_tasks,
                }
                if successful_tasks and failed_tasks:
                    result["job_status"] = "partial"
                elif failed_tasks:
                    result["job_status"] = "failed"
                    result["error_summary"] = "更新失敗：" + "、".join(
                        task["sendtask_id"] for task in failed_tasks
                    )
                return result

            admission = await job_manager.start_job(
                username,
                "依名稱更新任務",
                task_func,
                job_code=job_type,
                items=items,
                request_params={"ignore_archived": True},
            )
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown job type: {job_type}")

        return {"status": "success", "message": "任務已開始", **admission}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start job {job_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
