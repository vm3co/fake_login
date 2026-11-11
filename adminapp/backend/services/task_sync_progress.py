from contextlib import contextmanager
from contextvars import ContextVar
import asyncio
import logging
from dataclasses import replace

from backend.services.task_sync_entrypoints import TaskSyncStatuses, summarize_task_sync


_progress = ContextVar("task_sync_progress", default=None)
logger = logging.getLogger(__name__)


def exception_result(error):
    result = getattr(error, "results", None)
    if isinstance(result, TaskSyncStatuses):
        return summarize_task_sync(result, [])
    return result if isinstance(result, dict) else {}


def current_progress_result():
    progress = _progress.get()
    return progress.result if progress is not None else {}


def merge_job_results(previous, latest):
    previous = previous if isinstance(previous, dict) else {}
    latest = latest if isinstance(latest, dict) else {}
    merged = {**previous, **latest}
    results = {**previous.get("sync_results", {}), **latest.get("sync_results", {})}
    if results:
        from backend.services.task_sync_core import TaskSyncResult

        statuses = TaskSyncStatuses()
        for task_uuid, values in results.items():
            values = {**values, "changed_uuids": tuple(values["changed_uuids"])}
            statuses.results[task_uuid] = TaskSyncResult(**values)
        for source in (previous, latest):
            statuses.update({task_uuid: values["status"] for task_uuid, values in source.get("sync_results", {}).items()})
            statuses.update(source.get("sync_statuses", {}))
            for task in source.get("failed_tasks", []):
                task_uuid = task["sendtask_uuid"]
                statuses[task_uuid] = "error"
                statuses.errors[task_uuid] = task.get("reason", "sync_error")
                statuses.retryable_errors[task_uuid] = task.get("retryable", False)
            notifications = source.get("notification_errors", {})
            if isinstance(notifications, list):
                notifications = {item["sendtask_uuid"]: item.get("reason", "notification_error")
                                 for item in notifications}
            statuses.notification_errors.update(notifications)
        tasks = [task for source in (previous, latest) for key, value in source.items()
                 if key.endswith("_tasks") and isinstance(value, list)
                 for task in value if isinstance(task, dict) and "sendtask_uuid" in task]
        summary = summarize_task_sync(statuses, tasks)
        for key in ("skipped_count", "skipped_tasks"):
            summary.pop(key, None)
        merged.update(summary)
        if latest.get("job_status") in {"partial", "failed"}:
            merged["job_status"] = latest["job_status"]
    merged["changed_uuids"] = list(dict.fromkeys(
        previous.get("changed_uuids", []) + latest.get("changed_uuids", [])
    ))
    merged["backups_changed"] = bool(previous.get("backups_changed") or latest.get("backups_changed"))
    merged["reload_list"] = bool(previous.get("reload_list") or latest.get("reload_list") or merged.get("reload_list"))
    warnings = []
    for warning in previous.get("warnings", []) + latest.get("warnings", []) + merged.get("warnings", []):
        if warning not in warnings:
            warnings.append(warning)
    merged["warnings"] = warnings
    targets = {task["sendtask_uuid"]: task for source in (previous, latest)
               for task in source.get("target_tasks", [])}
    if targets:
        merged["target_tasks"] = list(targets.values())
        finished = set(merged.get("sync_statuses", {})) | {
            task["sendtask_uuid"] for task in merged.get("skipped_tasks", [])
        }
        merged["unfinished_tasks"] = [task for task_uuid, task in targets.items() if task_uuid not in finished]
        merged["unfinished_count"] = len(merged["unfinished_tasks"])
    return merged


class TaskSyncProgress:
    def __init__(self, save):
        self.save = save
        self.result = {}

    async def record(self, result):
        statuses = TaskSyncStatuses()
        statuses[result.task_uuid] = result.status
        statuses.results[result.task_uuid] = result
        self.result = merge_job_results(self.result, summarize_task_sync(statuses, []))
        await self.save(self.result)

    async def warning(self, task_uuid, stage, message):
        warning = {"task_uuid": task_uuid, "stage": stage, "message": message}
        self.result = merge_job_results(self.result, {"warnings": [warning]})
        await self.save(self.result)

    async def update(self, result):
        self.result = merge_job_results(self.result, result)
        await self.save(self.result)


@contextmanager
def track_task_sync(progress):
    token = _progress.set(progress)
    try:
        yield progress
    finally:
        _progress.reset(token)


async def report_warning(task_uuid, stage, message):
    progress = _progress.get()
    if progress is not None:
        try:
            await progress.warning(task_uuid, stage, message)
        except Exception as exc:
            logger.warning("Committed task warning could not be saved: %s", exc)


async def report_targets(tasks):
    await report_outcomes({"target_tasks": tasks})


async def report_outcomes(result):
    progress = _progress.get()
    if progress is not None:
        try:
            await progress.update(result)
        except Exception as exc:
            logger.warning("Task sync outcomes could not be saved: %s", exc)


async def report_commit(result, *, invalidate=False):
    progress = _progress.get()
    async def save(current):
        if progress is not None:
            try:
                await progress.record(current)
            except Exception as exc:
                warning = {"task_uuid": current.task_uuid, "stage": "progress", "message": str(exc)}
                logger.warning("Committed task progress could not be saved: %s", exc)
                return replace(current, warnings=(*current.warnings, warning))
        return current

    result = await save(result)
    if invalidate and result.changed_uuids:
        from backend.services.redis_client import RedisClient

        error = None
        for attempt in range(2):
            try:
                async def clear():
                    client = await RedisClient().get_client()
                    await client.delete(*(f"task:{task_uuid}:details" for task_uuid in result.changed_uuids))

                await asyncio.wait_for(clear(), timeout=0.5)
                error = None
                break
            except Exception as exc:
                error = exc
        if error is not None:
            warning = {"task_uuid": result.task_uuid, "stage": "cache_invalidation",
                       "message": str(error) or type(error).__name__, "attempts": 2}
            logger.warning("Committed task cache invalidation failed: %s", warning)
            result = replace(result, warnings=(*result.warnings, warning))
    if result.warnings:
        result = await save(result)
    return result