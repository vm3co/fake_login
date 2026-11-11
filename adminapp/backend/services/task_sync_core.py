from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.repository.models import SendLogDetail, SendLogStats, SendTask, TaskBackup
from backend.repository.task_reload_schema import task_reload_operations
from backend.services.se2_task_reader import SE2TaskReader, TaskNotFound, TaskReadError, TaskSnapshot, normalize_timestamp
from backend.services.task_sync import (
    ExpectedTaskVersion, TaskSyncConflict, task_lock_key, task_sync_transaction,
    transfer_task_to_backup,
)
from backend.services.task_archive_policy import should_archive_task


class TaskSyncAccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class TaskReloadIntent:
    operation_id: str
    actor: str
    source_generation: str

    def __post_init__(self):
        for value in (self.operation_id, self.source_generation):
            if not isinstance(value, str) or not value.strip() or len(value) > 36:
                raise ValueError("Invalid reload operation identity")
        if not isinstance(self.actor, str) or not self.actor.strip():
            raise ValueError("A trusted reload actor is required")


@dataclass(frozen=True)
class PreparedTaskSync:
    expected: ExpectedTaskVersion
    orgs: tuple[str, ...] | None
    snapshot: TaskSnapshot | None
    archive_at: int | None = None
    reload_intent: TaskReloadIntent | None = None


@dataclass(frozen=True)
class TaskSyncResult:
    status: str
    task_uuid: str
    generation: str | None
    revision: int | None
    backup_id: str | None
    committed: bool
    changed_uuids: tuple[str, ...]
    backups_changed: bool
    archive_transition: str | None = None
    source_generation: str | None = None
    operation_id: str | None = None
    actor: str | None = None
    replayed: bool = False
    source_revision: int | None = None


def _require_scope(owner_gids, orgs):
    if not isinstance(owner_gids, list) or any(not isinstance(group, str) for group in owner_gids):
        raise TaskSyncAccessDenied("Invalid task ownership")
    if orgs is not None and not set(owner_gids).intersection(orgs):
        raise TaskSyncAccessDenied("Task is outside the trusted organization scope")


def _calculate_stats(records):
    from backend.services.db_user import calc_stats

    return calc_stats([
        {**record, "plan_time": record.get("plan_time") or 0, "send_time": record.get("send_time") or 0}
        for record in records
    ])


def _snapshot_records(snapshot, task_uuid):
    from backend.services.db_user import SENDTASKS_COLUMNS, SENDLOG_COLUMNS, TESTCASE_DETAIL_COLUMNS

    if not isinstance(snapshot, TaskSnapshot):
        raise TaskReadError("invalid_snapshot")
    validated_task = SE2TaskReader._task_record(snapshot.task, task_uuid)
    create_ut = validated_task["sendtask_create_ut"]
    if normalize_timestamp(snapshot.create_ut) != create_ut:
        raise TaskReadError("snapshot_version_mismatch")
    metadata = SE2TaskReader._metadata(snapshot.metadata)
    person_count = metadata["summary"].get("person_count")
    if type(person_count) is not int or person_count < 0 or "stop_time_new" not in metadata:
        raise TaskReadError("incomplete_metadata")
    if not isinstance(snapshot.testcase, dict) or snapshot.testcase.get("testcase_uuid") != task_uuid:
        raise TaskReadError("invalid_testcase")
    if snapshot.sendlog_type != ("pretest" if validated_task["pre_test_enable"] else "test"):
        raise TaskReadError("snapshot_mode_mismatch")
    task_values = {key: deepcopy(validated_task[key]) for key in SENDTASKS_COLUMNS if key in validated_task}
    task_values.update(
        sendtask_create_ut=create_ut, is_pause=metadata["pause"],
        stop_time_new=metadata["stop_time_new"], person_count=person_count,
    )
    testcase_values = {
        key: deepcopy(snapshot.testcase[key]) for key in TESTCASE_DETAIL_COLUMNS if key in snapshot.testcase
    }
    stop_time = metadata["stop_time_new"]
    task_values["stop_time_new"] = -1 if stop_time in (-1, "-1") else normalize_timestamp(stop_time, allow_zero=True)
    logs = []
    seen = set()
    if not isinstance(snapshot.sendlogs, list):
        raise TaskReadError("invalid_sendlogs")
    for record in snapshot.sendlogs:
        if not isinstance(record, dict):
            raise TaskReadError("invalid_sendlog")
        log_uuid = record.get("uuid")
        if not isinstance(log_uuid, str) or not log_uuid or log_uuid in seen:
            raise TaskReadError("invalid_or_duplicate_sendlog_uuid")
        if record.get("sendtask_uuid", task_uuid) != task_uuid:
            raise TaskReadError("sendlog_task_mismatch")
        for field in ("target_email", "person_info", "template_uuid", "send_res"):
            if not isinstance(record.get(field), str):
                raise TaskReadError("incomplete_sendlog")
        for field in (
            "access_time", "access_src", "access_dev", "click_time", "click_src",
            "click_dev", "file_time", "file_src", "file_dev",
        ):
            if field not in record or (record[field] is not None and not isinstance(record[field], list)):
                raise TaskReadError("incomplete_sendlog_events")
        seen.add(log_uuid)
        values = {key: deepcopy(record[key]) for key in SENDLOG_COLUMNS if key in record}
        values.update(
            sendtask_uuid=task_uuid,
            plan_time=normalize_timestamp(record.get("plan_time"), allow_zero=True),
            send_time=normalize_timestamp(record.get("send_time"), allow_zero=True),
        )
        logs.append(values)
    return task_values, testcase_values, logs


class TaskSyncService:
    """Explicitly invoked core; no legacy entrypoints, notifications or cache I/O.

    orgs must come from trusted authentication: None is system/admin access.
    Prepare outside the write transaction. A conflict requires a fresh prepare,
    never replaying the old remote snapshot. Results are returned after commit.
    """

    def __init__(self, session_factory, reader, *, stats_calculator=_calculate_stats):
        self.session_factory = session_factory
        self.reader = reader
        self.stats_calculator = stats_calculator

    async def prepare(self, task_uuid: str, *, orgs, sendlog_type=None, archive_at=None, reload_intent=None) -> PreparedTaskSync:
        task_lock_key(task_uuid)
        if reload_intent is not None and not isinstance(reload_intent, TaskReloadIntent):
            raise ValueError("Reload intent must be trusted service data")
        if sendlog_type is not None and sendlog_type not in {"test", "pretest"}:
            raise TaskReadError("invalid_sendlog_type")
        if orgs is not None and (
            not isinstance(orgs, (list, tuple)) or not orgs
            or any(not isinstance(group, str) or not group for group in orgs)
        ):
            raise TaskSyncAccessDenied("A trusted organization scope is required")
        scope = None if orgs is None else tuple(orgs)
        async with self.session_factory() as session:
            row = (await session.execute(select(
                SendTask.local_generation_id, SendTask.sync_revision,
                SendTask.sendtask_owner_gid, SendTask.sendtask_create_ut, SendTask.pre_test_enable,
            ).where(SendTask.sendtask_uuid == task_uuid))).one_or_none()
        if row is None:
            expected = ExpectedTaskVersion(task_uuid, None, None)
        else:
            _require_scope(row.sendtask_owner_gid, scope)
            expected = ExpectedTaskVersion(task_uuid, row.local_generation_id, row.sync_revision)
        if reload_intent is not None and expected.generation != reload_intent.source_generation:
            raise TaskSyncConflict("The confirmed task generation is no longer current")
        mode = sendlog_type or ("pretest" if row is not None and row.pre_test_enable is True else "test")
        try:
            snapshot = deepcopy(await self.reader.read_task_snapshot(task_uuid, sendlog_type=mode))
            _snapshot_records(snapshot, task_uuid)
        except TaskNotFound:
            snapshot = None
        if snapshot is not None:
            _require_scope(snapshot.task.get("sendtask_owner_gid"), scope)
            if row is not None and reload_intent is None:
                normalize_timestamp(row.sendtask_create_ut)
            if archive_at is not None:
                task_values, _, _ = _snapshot_records(snapshot, task_uuid)
                should_archive_task(task_values, now=archive_at)
        return PreparedTaskSync(expected, scope, snapshot, archive_at, reload_intent)

    async def sync(self, task_uuid: str, *, orgs, sendlog_type=None, archive_at=None, reload_intent=None) -> TaskSyncResult:
        if reload_intent is not None:
            replay = await self._reload_receipt(task_uuid, reload_intent, orgs)
            if replay is not None:
                return replay
        try:
            return await self.apply(await self.prepare(
                task_uuid, orgs=orgs, sendlog_type=sendlog_type, archive_at=archive_at, reload_intent=reload_intent,
            ))
        except TaskSyncConflict:
            if reload_intent is not None:
                replay = await self._reload_receipt(task_uuid, reload_intent, orgs)
                if replay is not None:
                    return replay
            raise

    async def apply(self, prepared: PreparedTaskSync) -> TaskSyncResult:
        intent = prepared.reload_intent
        if intent is not None:
            replay = await self._reload_receipt(prepared.expected.task_uuid, intent, prepared.orgs)
            if replay is not None:
                return replay
        try:
            return await self._apply(prepared)
        except TaskSyncConflict:
            if intent is not None:
                replay = await self._reload_receipt(prepared.expected.task_uuid, intent, prepared.orgs)
                if replay is not None:
                    return replay
            raise

    async def _reload_receipt(self, task_uuid, intent, orgs):
        if not isinstance(intent, TaskReloadIntent):
            raise ValueError("Reload intent must be trusted service data")
        if orgs is not None and (
            not isinstance(orgs, (list, tuple)) or not orgs
            or any(not isinstance(group, str) or not group for group in orgs)
        ):
            raise TaskSyncAccessDenied("A trusted organization scope is required")
        async with self.session_factory() as session:
            receipt = (await session.execute(select(task_reload_operations).where(
                task_reload_operations.c.operation_id == intent.operation_id,
                task_reload_operations.c.task_uuid == task_uuid,
            ))).mappings().one_or_none()
        if receipt is None:
            return None
        if receipt["actor"] != intent.actor or receipt["source_generation"] != intent.source_generation:
            raise TaskSyncConflict("Reload operation identity was reused")
        _require_scope(receipt["owner_gids"], orgs)
        values = dict(receipt["result"])
        values["changed_uuids"] = tuple(values["changed_uuids"])
        return replace(TaskSyncResult(**values), replayed=True)

    async def _apply(self, prepared: PreparedTaskSync) -> TaskSyncResult:
        expected = prepared.expected
        intent = prepared.reload_intent
        if intent is not None and (expected.generation is None or expected.generation != intent.source_generation):
            raise TaskSyncConflict("Reload requires the confirmed current generation")
        snapshot = deepcopy(prepared.snapshot)
        mapped = None if snapshot is None else _snapshot_records(snapshot, expected.task_uuid)
        backup_id = None
        backups_changed = False
        archive_transition = None
        async with task_sync_transaction(self.session_factory, expected) as locked:
            task = locked.task
            if task is not None:
                _require_scope(task.sendtask_owner_gid, prepared.orgs)
            owner_gids = list(task.sendtask_owner_gid) if task is not None else []
            if snapshot is None:
                if task is None:
                    if prepared.orgs is not None:
                        backup = await locked.session.scalar(select(TaskBackup.backup_id).where(
                            TaskBackup.source_task_uuid == expected.task_uuid,
                            TaskBackup.owner_gids.overlap(list(prepared.orgs)),
                        ).limit(1))
                        if backup is None:
                            raise TaskSyncAccessDenied("Missing task has no authorized local ownership")
                    status, generation, revision = "unchanged", None, None
                else:
                    transfer = await transfer_task_to_backup(locked, reason="remote_missing")
                    backup_id = transfer.backup_id
                    backups_changed = True
                    status, generation, revision = "backed_up", None, None
            else:
                _require_scope(snapshot.task.get("sendtask_owner_gid"), prepared.orgs)
                task_values, testcase_values, logs = mapped
                created = task is None
                was_archived = task is not None and task.is_archived is True
                reloaded = intent is not None
                recreated = task is not None and not reloaded and normalize_timestamp(task.sendtask_create_ut) != task_values["sendtask_create_ut"]
                if recreated or reloaded:
                    transfer = await transfer_task_to_backup(locked, reason="manual_reload" if reloaded else "remote_recreated")
                    backup_id = transfer.backup_id
                    backups_changed = True
                if created or recreated or reloaded:
                    generation, revision = str(uuid4()), 0
                    task = SendTask(
                        **task_values, **testcase_values,
                        local_generation_id=generation, sync_revision=0, is_archived=False,
                    )
                    locked.session.add(task)
                else:
                    await locked.lock_details()
                    generation, revision = task.local_generation_id, task.sync_revision + 1
                    for key, value in {**task_values, **testcase_values}.items():
                        setattr(task, key, value)
                if prepared.archive_at is not None:
                    archived = should_archive_task(task, now=prepared.archive_at)
                    task.is_archived = archived
                    if archived != was_archived:
                        archive_transition = "archived" if archived else "unarchived"
                await locked.session.flush()
                for values in logs:
                    statement = insert(SendLogDetail).values(**values)
                    statement = statement.on_conflict_do_update(
                        index_elements=[SendLogDetail.uuid],
                        set_={key: getattr(statement.excluded, key) for key in values if key not in {"uuid", "sendtask_uuid"}},
                        where=SendLogDetail.sendtask_uuid == expected.task_uuid,
                    ).returning(SendLogDetail.uuid)
                    if (await locked.session.execute(statement)).scalar_one_or_none() is None:
                        raise TaskSyncConflict("Sendlog UUID already belongs to another task")
                records = (await locked.session.execute(select(SendLogDetail.__table__).where(
                    SendLogDetail.sendtask_uuid == expected.task_uuid,
                ))).mappings().all()
                stats_values = {"sendtask_uuid": expected.task_uuid, **self.stats_calculator(records)}
                statement = insert(SendLogStats).values(**stats_values)
                await locked.session.execute(statement.on_conflict_do_update(
                    index_elements=[SendLogStats.sendtask_uuid],
                    set_={key: getattr(statement.excluded, key) for key in stats_values if key != "sendtask_uuid"},
                ))
                backups_changed |= await self._observe_backups(
                    locked.session, expected.task_uuid, task_values["sendtask_create_ut"], prepared.orgs,
                )
                status = "reloaded" if reloaded else "recreated" if recreated else "added" if created else "updated"
            changed = () if status == "unchanged" else (expected.task_uuid,)
            result = TaskSyncResult(
                status, expected.task_uuid, generation, revision, backup_id, True,
                changed, backups_changed, archive_transition,
                source_generation=expected.generation if intent else None,
                operation_id=intent.operation_id if intent else None, actor=intent.actor if intent else None,
                source_revision=expected.revision if intent else None,
            )
            if intent is not None:
                await locked.session.execute(insert(task_reload_operations).values(
                    operation_id=intent.operation_id, task_uuid=expected.task_uuid, actor=intent.actor,
                    owner_gids=owner_gids, source_generation=expected.generation, result=asdict(result),
                ))
        return result

    @staticmethod
    async def _observe_backups(session, task_uuid, create_ut, orgs):
        filters = [TaskBackup.source_task_uuid == task_uuid]
        if orgs is not None:
            filters.append(TaskBackup.owner_gids.overlap(list(orgs)))
        backups = (await session.execute(select(TaskBackup).where(*filters).order_by(
            TaskBackup.backup_id,
        ).with_for_update())).scalars().all()
        now = datetime.now(timezone.utc)
        for backup in backups:
            backup.latest_remote_status = "present"
            backup.last_remote_checked_at = now
            backup.last_remote_create_ut = create_ut
            try:
                old_create_ut = normalize_timestamp(backup.source_create_ut)
            except TaskReadError:
                continue
            if old_create_ut != create_ut and backup.recreated_detected_at is None:
                backup.recreated_detected_at = now
        return bool(backups)