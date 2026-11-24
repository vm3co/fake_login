import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from backend.repository.models import TaskBackup
from backend.services.backup_observation import update_backup_observations
from backend.services.se2_task_reader import SE2TaskReader, TaskNotFound, TaskReadError
from backend.services.task_backup_access import scoped_backups
from backend.services.task_sync_progress import report_outcomes


class BackupCheckCancelled(asyncio.CancelledError):
    def __init__(self, results):
        super().__init__("Backup check cancelled")
        self.results = results


async def select_backup_targets(session_factory, backup_ids, scope):
    if scope is not None and (not isinstance(scope, (tuple, list)) or not scope or any(
        not isinstance(org, str) or not org for org in scope
    )):
        raise HTTPException(status_code=403, detail="A trusted organization scope is required")
    if not isinstance(backup_ids, list) or not backup_ids or any(
        not isinstance(value, str) or not value.strip() or len(value) > 36 for value in backup_ids
    ):
        raise HTTPException(status_code=400, detail="Explicit backup_ids are required")
    selected = list(dict.fromkeys(backup_ids))
    async with session_factory() as session:
        backups = (await session.scalars(scoped_backups(scope).where(TaskBackup.backup_id.in_(selected)))).all()
        if len(backups) != len(selected):
            raise HTTPException(status_code=404, detail="Selected backups are unavailable")
        groups = {}
        for backup in sorted(backups, key=lambda value: value.backup_id):
            group = groups.setdefault(backup.source_task_uuid, {"sendtask_uuid": backup.source_task_uuid,
                "sendtask_id": backup.sendtask_id, "backup_ids": [], "modes": set()})
            group["backup_ids"].append(backup.backup_id)
            group["modes"].add("pretest" if backup.task_snapshot.get("pre_test_enable") is True else "test")
        return [{**group, "sendlog_type": "pretest" if group["modes"] == {"pretest"} else "test"}
                for _, group in sorted(groups.items())]


def check_summary(targets, observations, failures):
    observed_ids = {row["backup_id"] for row in observations}
    failed_sources = {row["source_task_uuid"] for row in failures}
    changed = [row["backup_id"] for row in observations if row["applied"]]
    return {
        "checked_count": len(observations), "failed_count": len(failures),
        "backup_check_items": {target["sendtask_uuid"]: "backup_check_error" if target["sendtask_uuid"] in failed_sources
                             else "backup_check_" + next(row["latest_remote_status"] for row in observations
                                 if row["source_task_uuid"] == target["sendtask_uuid"])
                               for target in targets if target["sendtask_uuid"] in failed_sources or any(
                                   row["source_task_uuid"] == target["sendtask_uuid"] for row in observations)},
        "backup_observations": observations, "backup_check_errors": failures,
        "changed_backup_ids": changed, "backups_changed": bool(changed), "changed_uuids": [], "reload_list": False,
        "unchecked_backup_ids": [backup_id for target in targets for backup_id in target["backup_ids"]
                                 if backup_id not in observed_ids],
        "job_status": "partial" if failures and any(row["source_task_uuid"] not in failed_sources for row in observations)
                      else "failed" if failures else "completed",
    }


class BackupCheckService:
    def __init__(self, session_factory, reader):
        self.session_factory = session_factory
        self.reader = reader

    async def check(self, backup_ids, *, scope, on_source=None):
        targets = await select_backup_targets(self.session_factory, backup_ids, scope)
        observations, failures = [], []
        try:
            for target in targets:
                await asyncio.sleep(0)
                try:
                    await select_backup_targets(self.session_factory, target["backup_ids"], scope)
                except HTTPException:
                    failures.append({"source_task_uuid": target["sendtask_uuid"], "backup_ids": target["backup_ids"],
                                     "reason": "Selected backups are unavailable"})
                    await report_outcomes(check_summary(targets, observations, failures))
                    continue
                checked_at = datetime.now(timezone.utc)
                create_ut, reason = None, None
                try:
                    response = await self.reader.read_sendtask(target["sendtask_uuid"], sendlog_type=target["sendlog_type"])
                    record = SE2TaskReader._task_record(response["data"], target["sendtask_uuid"])
                    create_ut = record["sendtask_create_ut"]
                    status = "present"
                except TaskNotFound:
                    status = "missing"
                except TaskReadError as exc:
                    status, reason = "error", str(exc)
                try:
                    async with self.session_factory() as session:
                        async with session.begin():
                            selected = (await session.scalars(scoped_backups(scope).where(
                                TaskBackup.backup_id.in_(target["backup_ids"]),
                            ).order_by(TaskBackup.backup_id).with_for_update())).all()
                            if len(selected) != len(target["backup_ids"]):
                                raise HTTPException(status_code=404, detail="Selected backups are unavailable")
                            rows = await update_backup_observations(session, task_uuid=target["sendtask_uuid"], scope=scope,
                                checked_at=checked_at, status=status, create_ut=create_ut, backup_ids=target["backup_ids"])
                except Exception as exc:
                    failures.append({"source_task_uuid": target["sendtask_uuid"], "backup_ids": target["backup_ids"], "reason": str(exc)})
                    await report_outcomes(check_summary(targets, observations, failures))
                    continue
                observations.extend(rows)
                if status == "error" or any(row["latest_remote_status"] == "error" and row["applied"] for row in rows):
                    failures.append({"source_task_uuid": target["sendtask_uuid"], "backup_ids": target["backup_ids"],
                                     "reason": reason or "Invalid source version"})
                saved = asyncio.create_task(report_outcomes(check_summary(targets, observations, failures)))
                try:
                    await asyncio.shield(saved)
                except asyncio.CancelledError:
                    await saved
                    raise
                if on_source is not None:
                    await on_source(target, rows, status)
        except asyncio.CancelledError:
            raise BackupCheckCancelled(check_summary(targets, observations, failures)) from None
        return check_summary(targets, observations, failures)