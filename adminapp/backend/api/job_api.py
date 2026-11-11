import asyncio

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from datetime import datetime, timezone
from dataclasses import asdict
import time
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
from backend.services.task_sync_entrypoints import TaskSyncStatuses, TaskSyncCancelled, summarize_task_sync
from backend.services.task_sync_core import TaskSyncAccessDenied, TaskReloadIntent
from backend.services.se2_task_reader import TaskNotFound

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


async def sync_job_items(accepted_items, job_id, *, orgs):
    statuses = TaskSyncStatuses()
    try:
        for item in accepted_items:
            task_uuid = item["sendtask_uuid"]
            try:
                await job_manager.mark_item(job_id, task_uuid, "running")
            except Exception as exc:
                statuses.notification_errors[task_uuid] = str(exc)
            try:
                result = await db_user.refresh_sendlog_stats([task_uuid], orgs=orgs)
            except Exception as exc:
                statuses[task_uuid] = "error"
                statuses.errors[task_uuid] = str(exc)
                try:
                    await job_manager.mark_item(job_id, task_uuid, "failed", str(exc))
                except Exception as reporting_error:
                    statuses.notification_errors[task_uuid] = str(reporting_error)
                continue
            statuses.update(result)
            statuses.results.update(getattr(result, "results", {}))
            statuses.errors.update(getattr(result, "errors", {}))
            statuses.notification_errors.update(getattr(result, "notification_errors", {}))
            status = result.get(task_uuid, "error")
            try:
                await job_manager.mark_item(job_id, task_uuid, "failed" if status == "error" else "completed", status)
            except Exception as exc:
                statuses.notification_errors[task_uuid] = str(exc)
    except TaskSyncCancelled as exc:
        statuses.update(exc.results)
        statuses.results.update(exc.results.results)
        statuses.errors.update(exc.results.errors)
        raise TaskSyncCancelled(statuses) from None
    except asyncio.CancelledError:
        raise TaskSyncCancelled(statuses) from None
    return summarize_task_sync(statuses, accepted_items)


async def reload_job_items(accepted_items, job_id, *, orgs, actor, generations):
    statuses = TaskSyncStatuses()
    audit = []
    archive_at = int(time.time())
    try:
        for item in accepted_items:
            task_uuid = item["sendtask_uuid"]
            try:
                await job_manager.mark_item(job_id, task_uuid, "running")
            except Exception as exc:
                statuses.notification_errors[task_uuid] = str(exc)
            try:
                result = await db_user.get_task_sync().sync(
                    task_uuid, orgs=orgs, archive_at=archive_at,
                    reload_intent=TaskReloadIntent(job_id, actor, generations[task_uuid]),
                )
            except Exception as exc:
                statuses[task_uuid] = "error"
                statuses.errors[task_uuid] = str(exc)
                try:
                    await job_manager.mark_item(job_id, task_uuid, "failed", str(exc))
                except Exception as reporting_error:
                    statuses.notification_errors[task_uuid] = str(reporting_error)
                continue
            statuses[task_uuid] = result.status
            statuses.results[task_uuid] = result
            audit.append(asdict(result))
            try:
                await job_manager.mark_item(job_id, task_uuid, "completed", result.status)
            except Exception as exc:
                statuses.notification_errors[task_uuid] = str(exc)
    except asyncio.CancelledError:
        raise TaskSyncCancelled(statuses) from None
    summary = summarize_task_sync(statuses, accepted_items)
    summary["reload_results"] = audit
    return summary

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
    blocking_job_ids = {
        item.blocking_job_id
        for item in job_items
        if item.blocking_job_id
    }
    blocking_jobs = await db_controller.get(
        JobRun,
        filters={"job_id": list(blocking_job_ids)},
    ) if blocking_job_ids else []
    blocking_jobs_by_id = {job.job_id: job for job in blocking_jobs}
    items_by_job = {}
    for item in job_items:
        blocking_job = blocking_jobs_by_id.get(item.blocking_job_id)
        items_by_job.setdefault(item.job_id, []).append({
            "sendtask_uuid": item.sendtask_uuid,
            "sendtask_id": item.sendtask_id,
            "status": item.status,
            "reason": item.reason,
            "blocking_username": blocking_job.owner_username if blocking_job else None,
        })
    for items in items_by_job.values():
        items.sort(key=lambda item: (item["status"] == "skipped", item["sendtask_id"]))
    exclusive_jobs = [
        job for job in jobs
        if job.execution_class == "maintenance_exclusive"
        and job.status in {"queued", "claiming", "running", "cancel_requested"}
    ]
    response = []
    for job in jobs:
        items = items_by_job.get(job.job_id, [])
        excluded_count = sum(
            item["status"] == "skipped" and item["reason"] in {"duplicate_active", "claim_failed"}
            for item in items
        )
        blocking_usernames = sorted({
            item["blocking_username"]
            for item in items
            if item["reason"] == "duplicate_active" and item["blocking_username"]
        })
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
            "requested_count": len(items),
            "accepted_count": len(items) - excluded_count,
            "excluded_count": excluded_count,
            "blocking_usernames": blocking_usernames,
            "items": items,
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
                return await db_user.sync_today_created_tasks(orgs=orgs)

            admission = await job_manager.start_job(username, "檢查今日建立任務", task_func, job_code=job_type)

        elif job_type == "update_mtmpl":
            async def task_func():
                result = await db_user.refresh_mtmpl()
                if result.get("synced_count", 0) == 0:
                    raise Exception("從 SE2 獲取郵件樣板失敗")
                return {
                    "synced_count": result["synced_count"],
                    "added_count": result["added_count"],
                    "added_templates": result["added_templates"],
                    "removed_count": result["removed_count"],
                    "removed_templates": result["removed_templates"],
                }

            admission = await job_manager.start_job(username, "更新郵件樣板列表", task_func, job_code=job_type)

        elif job_type == "check_sendtasks":
            orgs = get_sendtask_scope(current_user)
            # Logic from check_sendtasks
            async def task_func():
                result = await db_user.sync_sendtasks(orgs=orgs)

                def task_summary(task):
                    return {
                        "sendtask_uuid": task.get("sendtask_uuid"),
                        "sendtask_id": task.get("sendtask_id", "Unknown"),
                    }

                summary = {
                    "added_count": len(result["added"]),
                    "added_tasks": [task_summary(task) for task in result["added"]],
                    "updated_count": len(result["changed"]),
                    "updated_tasks": [task_summary(task) for task in result["changed"]],
                    "deleted_count": result["deleted"],
                    "deleted_tasks": result.get("deleted_tasks", []),
                    "archived_count": result["archived"],
                    "archived_tasks": result.get("archived_tasks", []),
                }
                if result.get("versioned"):
                    summary.update({
                        "job_status": "partial" if result["failed_tasks"] and result.get("changed_uuids") else "failed" if result["failed_tasks"] else "completed",
                        "status": result["status"],
                        "recreated_count": len(result["recreated"]),
                        "recreated_tasks": result["recreated"],
                        "backed_up_count": len(result["backed_up"]),
                        "backed_up_tasks": result["backed_up"],
                        "unarchived_count": len(result["unarchived_tasks"]),
                        "unarchived_tasks": result["unarchived_tasks"],
                        "failed_count": len(result["failed_tasks"]),
                        "failed_tasks": result["failed_tasks"],
                        "changed_uuids": result["changed_uuids"],
                        "backups_changed": result["backups_changed"],
                    })
                return summary

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
                return await sync_job_items(accepted_items, job_id, orgs=orgs)

            admission = await job_manager.start_job(
                username,
                "更新任務統計",
                task_func,
                job_code=job_type,
                items=items,
                request_params={"ignore_archived": params.get("ignore_archived", False)},
            )

        elif job_type == "force_reload_sendtask":
            if current_user.get("user_type") == "customer":
                raise HTTPException(status_code=403, detail="客戶不可操作備援重匯")
            orgs = get_sendtask_scope(current_user)
            if orgs is not None and not orgs:
                raise HTTPException(status_code=403, detail="無可操作的組織範圍")
            if params.get("confirm_reload") is not True:
                raise HTTPException(status_code=400, detail="必須明確確認先備援再重新匯入")
            requested = params.get("uuids")
            if (
                not isinstance(requested, list) or not requested
                or any(not isinstance(value, str) or not value.strip() or len(value) > 36 for value in requested)
                or "backup_id" in params or "backup_ids" in params
            ):
                raise HTTPException(status_code=400, detail="必須指定現行任務 UUID 清單，不接受備援 ID")
            tasks = await db_controller.get(SendTask, filters={"sendtask_uuid": list(dict.fromkeys(requested))})
            tasks = filter_tasks_by_scope(tasks, orgs)
            if not tasks:
                raise HTTPException(status_code=403, detail="找不到有權操作的現行任務")
            generations = {task.sendtask_uuid: task.local_generation_id for task in tasks}
            items = [{"sendtask_uuid": task.sendtask_uuid, "sendtask_id": task.sendtask_id} for task in tasks]

            async def task_func(*, accepted_items, job_id):
                return await reload_job_items(accepted_items, job_id, orgs=orgs, actor=username, generations=generations)

            admission = await job_manager.start_job(
                username, "備援後重新匯入任務", task_func, job_code=job_type, items=items,
                request_params={"confirm_reload": True, "source_generations": generations},
            )

        elif job_type == "upsert_selected_sendtasks":
            requested_uuids = params.get("uuids", [])
            if not requested_uuids:
                raise HTTPException(status_code=400, detail="未指定任務 UUID")

            orgs = get_sendtask_scope(current_user)
            items = []
            for task_uuid in dict.fromkeys(requested_uuids):
                try:
                    record = await db_user.authorize_sync_candidate(task_uuid, orgs=orgs)
                except (TaskSyncAccessDenied, TaskNotFound):
                    continue
                items.append({
                    "sendtask_uuid": task_uuid,
                    "sendtask_id": record.get("sendtask_id", "Unknown"),
                })
            if not items:
                raise HTTPException(status_code=403, detail="無權存取指定任務或任務已不存在")

            async def task_func(*, accepted_items, job_id):
                return await sync_job_items(accepted_items, job_id, orgs=orgs)

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
