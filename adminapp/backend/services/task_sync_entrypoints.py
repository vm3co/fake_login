import asyncio
import time
from dataclasses import asdict

from backend.services.task_sync_core import TaskSyncAccessDenied
from backend.services.task_sync import TaskSyncConflict


class TaskSyncStatuses(dict):
    def __init__(self):
        super().__init__()
        self.results = {}
        self.errors = {}
        self.notification_errors = {}
        self.retryable_errors = {}

    def merge(self, other):
        self.update(other)
        for name in ("results", "errors", "notification_errors", "retryable_errors"):
            getattr(self, name).update(getattr(other, name, {}))


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
    uuids = list(dict.fromkeys(uuids))
    from backend.services.task_sync_progress import report_outcomes, report_targets

    await report_targets([{"sendtask_uuid": task_uuid, "sendtask_id": task_uuid} for task_uuid in uuids])
    archive_at = int(time.time())
    try:
        for task_uuid in dict.fromkeys(uuids):
            await asyncio.sleep(0)
            try:
                result = await core.sync(task_uuid, orgs=orgs, archive_at=archive_at)
            except Exception as exc:
                statuses[task_uuid] = "error"
                statuses.errors[task_uuid] = str(exc)
                statuses.retryable_errors[task_uuid] = isinstance(exc, TaskSyncConflict)
                await report_outcomes(summarize_task_sync(statuses, []))
                continue
            statuses[task_uuid] = result.status
            statuses.results[task_uuid] = result
            if on_result is not None:
                try:
                    await on_result(result)
                except Exception as exc:
                    statuses.notification_errors[task_uuid] = str(exc)
                    from backend.services.task_sync_progress import report_warning

                    await report_warning(task_uuid, "notification", str(exc))
    except asyncio.CancelledError as exc:
        if isinstance(getattr(exc, "results", None), TaskSyncStatuses):
            statuses.merge(exc.results)
        raise TaskSyncCancelled(statuses) from None
    return statuses


def summarize_task_sync(statuses, tasks):
    names = {task["sendtask_uuid"]: task.get("sendtask_id", "Unknown") for task in tasks}
    groups = {key: [] for key in (
        "added", "updated", "recreated", "reloaded", "backed_up", "unchanged",
        "archived", "unarchived", "successful", "failed", "conflict",
    )}
    for task_uuid, status in statuses.items():
        task = {"sendtask_uuid": task_uuid, "sendtask_id": names.get(task_uuid, task_uuid)}
        if status == "error":
            failed_task = {**task, "reason": statuses.errors.get(task_uuid, "sync_error"),
                           "retryable": statuses.retryable_errors.get(task_uuid, False)}
            groups["failed"].append(failed_task)
            if failed_task["retryable"]:
                groups["conflict"].append(failed_task)
        else:
            groups["successful"].append(task)
            if status in groups:
                groups[status].append(task)
        result = statuses.results.get(task_uuid)
        if result is not None and result.archive_transition in {"archived", "unarchived"}:
            groups[result.archive_transition].append(task)
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
        "sync_results": {task_uuid: asdict(result) for task_uuid, result in statuses.results.items()},
        "reload_list": any(result.status in {"added", "recreated", "reloaded", "backed_up"}
                           or result.archive_transition for result in statuses.results.values()),
        "warnings": [warning for result in statuses.results.values() for warning in result.warnings] + [
            {"task_uuid": task_uuid, "stage": "post_commit", "message": message}
            for task_uuid, message in statuses.notification_errors.items()
        ],
        "skipped_count": 0, "skipped_tasks": [],
    }