import asyncio
import time

from backend.services.task_sync_core import TaskSyncAccessDenied


class TaskSyncStatuses(dict):
    def __init__(self):
        super().__init__()
        self.results = {}
        self.errors = {}
        self.notification_errors = {}


class TaskSyncCancelled(asyncio.CancelledError):
    def __init__(self, results):
        super().__init__("Task sync cancelled")
        self.results = results


class TaskSyncIncomplete(RuntimeError):
    def __init__(self, results):
        super().__init__("Task synchronization did not complete successfully")
        self.results = results


async def sync_task_batch(core, uuids, *, orgs, on_result=None):
    if orgs is not None and (
        not isinstance(orgs, (list, tuple)) or not orgs
        or any(not isinstance(group, str) or not group for group in orgs)
    ):
        raise TaskSyncAccessDenied("A trusted organization scope is required")
    statuses = TaskSyncStatuses()
    archive_at = int(time.time())
    try:
        for task_uuid in dict.fromkeys(uuids):
            await asyncio.sleep(0)
            try:
                result = await core.sync(task_uuid, orgs=orgs, archive_at=archive_at)
            except Exception as exc:
                statuses[task_uuid] = "error"
                statuses.errors[task_uuid] = str(exc)
                continue
            statuses[task_uuid] = result.status
            statuses.results[task_uuid] = result
            if on_result is not None:
                try:
                    await on_result(result)
                except Exception as exc:
                    statuses.notification_errors[task_uuid] = str(exc)
    except asyncio.CancelledError:
        raise TaskSyncCancelled(statuses) from None
    return statuses


def summarize_task_sync(statuses, tasks):
    names = {task["sendtask_uuid"]: task.get("sendtask_id", "Unknown") for task in tasks}
    groups = {key: [] for key in ("added", "updated", "recreated", "backed_up", "successful", "failed")}
    for task_uuid, status in statuses.items():
        task = {"sendtask_uuid": task_uuid, "sendtask_id": names.get(task_uuid, task_uuid)}
        if status == "error":
            groups["failed"].append({**task, "reason": statuses.errors.get(task_uuid, "sync_error")})
        else:
            groups["successful"].append(task)
            if status in groups:
                groups[status].append(task)
    failed = bool(groups["failed"])
    return {
        **{key + "_tasks": value for key, value in groups.items()},
        **{key + "_count": len(value) for key, value in groups.items()},
        "job_status": "partial" if failed and groups["successful"] else "failed" if failed else "completed",
        "changed_uuids": list(dict.fromkeys(
            task_uuid for result in statuses.results.values() for task_uuid in result.changed_uuids
        )),
        "backups_changed": any(result.backups_changed for result in statuses.results.values()),
        "sync_statuses": dict(statuses),
        "notification_errors": statuses.notification_errors,
        "skipped_count": 0, "skipped_tasks": [],
    }