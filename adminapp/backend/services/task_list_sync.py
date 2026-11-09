import asyncio
import time

from sqlalchemy import or_, select

from backend.repository.models import SendTask, TaskBackup
from backend.services.se2_task_reader import SE2TaskReader, TaskNotFound, TaskReadError, normalize_timestamp
from backend.services.task_archive_policy import should_archive_task
from backend.services.task_sync_core import TaskSyncAccessDenied, _require_scope


class TaskListSyncService:
    """Explicit opt-in list orchestration; TaskSyncService owns all task writes."""

    def __init__(self, core, *, clock=time.time, batch_size=20):
        if type(batch_size) is not int or not 1 <= batch_size <= 100:
            raise ValueError("batch_size must be between 1 and 100")
        self.core = core
        self.clock = clock
        self.batch_size = batch_size

    async def sync(self, *, orgs, on_result=None):
        if orgs is not None and (
            not isinstance(orgs, (list, tuple)) or not orgs
            or any(not isinstance(group, str) or not group for group in orgs)
        ):
            raise TaskSyncAccessDenied("A trusted organization scope is required")
        scope = None if orgs is None else tuple(orgs)
        now = normalize_timestamp(int(self.clock()))
        remote = await self.core.reader.read_sendtasks()
        if not isinstance(remote, list):
            raise TaskReadError("invalid_task_list")
        remote_map = {}
        remote_outside_scope = set()
        seen = set()
        for record in remote:
            record = SE2TaskReader._task_record(record)
            task_uuid = record["sendtask_uuid"]
            if task_uuid in seen:
                raise TaskReadError("duplicate_task_list_uuid")
            seen.add(task_uuid)
            if scope is None or set(record["sendtask_owner_gid"]).intersection(scope):
                remote_map[task_uuid] = record
            else:
                remote_outside_scope.add(task_uuid)
        async with self.core.session_factory() as session:
            tasks = select(SendTask.sendtask_uuid, SendTask.sendtask_id, SendTask.pre_test_enable)
            backups = select(TaskBackup.source_task_uuid, TaskBackup.sendtask_id, TaskBackup.task_snapshot).order_by(
                TaskBackup.backed_up_at, TaskBackup.backup_id,
            )
            blocked = set()
            if scope is not None:
                tasks = tasks.where(SendTask.sendtask_owner_gid.overlap(list(scope)))
                backups = backups.where(TaskBackup.owner_gids.overlap(list(scope)))
                blocked = set((await session.scalars(select(SendTask.sendtask_uuid).where(
                    or_(SendTask.sendtask_owner_gid.is_(None), ~SendTask.sendtask_owner_gid.overlap(list(scope))),
                ))).all())
            local = {row.sendtask_uuid: row for row in (await session.execute(tasks)).all()}
            history = {row.source_task_uuid: row for row in (await session.execute(backups)).all()}
        candidates = sorted((set(local) | set(history) | set(remote_map)) - blocked - remote_outside_scope)
        result = {
            "versioned": True, "status": "success", "results": [], "failed_tasks": [],
            "changed_uuids": [], "backups_changed": False, "skipped": [], "notification_errors": [],
            **{key: [] for key in ("added", "changed", "recreated", "backed_up", "archived_tasks", "unarchived_tasks")},
        }
        for index, task_uuid in enumerate(candidates):
            if index % self.batch_size == 0:
                await asyncio.sleep(0)
            known = task_uuid in local or task_uuid in history
            record = remote_map.get(task_uuid)
            fallback = local.get(task_uuid) or history.get(task_uuid)
            summary = {
                "sendtask_uuid": task_uuid,
                "sendtask_id": record["sendtask_id"] if record else fallback.sendtask_id,
            }
            try:
                if task_uuid in local:
                    pretest = local[task_uuid].pre_test_enable
                elif record is not None:
                    pretest = record["pre_test_enable"]
                else:
                    pretest = history[task_uuid].task_snapshot.get("pre_test_enable", False)
                mode = "pretest" if pretest is True else "test"
                try:
                    detail = await self.core.reader.read_sendtask(task_uuid, sendlog_type=mode)
                    task = SE2TaskReader._task_record(detail["data"], task_uuid)
                    _require_scope(task["sendtask_owner_gid"], scope)
                    metadata = SE2TaskReader._metadata(detail.get("metadata"))
                except TaskNotFound:
                    if not known:
                        raise
                else:
                    if not known and should_archive_task({**task, "stop_time_new": metadata["stop_time_new"]}, now=now):
                        result["skipped"].append(summary)
                        continue
                synced = await self.core.sync(task_uuid, orgs=scope, sendlog_type=mode, archive_at=now)
            except Exception as exc:
                result["failed_tasks"].append({**summary, "reason": str(exc)})
                continue
            result["results"].append(synced)
            result["changed_uuids"].extend(synced.changed_uuids)
            result["backups_changed"] |= synced.backups_changed
            key = {"added": "added", "updated": "changed", "recreated": "recreated", "backed_up": "backed_up"}.get(synced.status)
            if key:
                result[key].append(summary)
            if synced.archive_transition:
                result[synced.archive_transition + "_tasks"].append(summary)
            if on_result is not None:
                try:
                    await on_result(synced)
                except Exception as exc:
                    result["notification_errors"].append({**summary, "reason": str(exc)})
        result["status"] = "partial" if result["failed_tasks"] else "success"
        result["archived"] = len(result["archived_tasks"])
        result["deleted"] = 0
        result["deleted_tasks"] = []
        return result