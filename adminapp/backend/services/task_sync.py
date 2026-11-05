from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b
import json

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repository.models import Mtmpl, SendLogDetail, SendLogStats, SendTask, TaskBackup, TaskBackupDetail


class TaskSyncConflict(RuntimeError):
    """Discard prepared data and prepare again before retrying."""

    retryable = True


class TaskSyncLockTimeout(TaskSyncConflict):
    pass


@dataclass(frozen=True)
class ExpectedTaskVersion:
    task_uuid: str
    generation: str | None
    revision: int | None

    def __post_init__(self):
        task_lock_key(self.task_uuid)
        if self.generation is None:
            if self.revision is not None:
                raise ValueError("Absent tasks must not have a revision")
        elif not isinstance(self.generation, str) or not self.generation or (
            type(self.revision) is not int or self.revision < 0
        ):
            raise ValueError("Invalid expected task version")


def task_lock_key(task_uuid: str) -> int:
    if not isinstance(task_uuid, str) or not task_uuid or len(task_uuid) > 36:
        raise ValueError("Invalid task UUID")
    digest = blake2b(
        task_uuid.encode("utf-8"), digest_size=8, person=b"tsb-task-sync-v1",
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


async def read_expected_task_version(session_factory, task_uuid: str) -> ExpectedTaskVersion:
    task_lock_key(task_uuid)
    async with session_factory() as session:
        row = (await session.execute(select(
            SendTask.local_generation_id, SendTask.sync_revision,
        ).where(SendTask.sendtask_uuid == task_uuid))).one_or_none()
    return ExpectedTaskVersion(task_uuid, row[0], row[1]) if row else ExpectedTaskVersion(task_uuid, None, None)


@dataclass
class LockedTask:
    session: AsyncSession
    expected: ExpectedTaskVersion
    task: SendTask | None
    _active: bool = False
    _backup_result: "BackupTransferResult | None" = None

    def require_active(self):
        if not self._active or not self.session.in_transaction():
            raise RuntimeError("Task guard must be used inside task_sync_transaction")

    async def lock_details(self) -> list[SendLogDetail]:
        """Call after the task lock and before copying the backup snapshot."""
        self.require_active()
        return list((await self.session.execute(
            select(SendLogDetail)
            .where(SendLogDetail.sendtask_uuid == self.expected.task_uuid)
            .order_by(SendLogDetail.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalars().all())


@dataclass(frozen=True)
class BackupTransferResult:
    backup_id: str | None
    source_task_uuid: str
    source_generation: str | None
    reason: str
    detail_count: int
    created: bool


def _snapshot_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Snapshot datetime requires an explicit timezone")
        return value.isoformat()
    raise TypeError(f"Unsupported snapshot type: {type(value).__name__}")


def _json_snapshot(value):
    return json.loads(json.dumps(value, default=_snapshot_value, allow_nan=False))


async def transfer_task_to_backup(locked: LockedTask, *, reason: str) -> BackupTransferResult:
    """Copy then remove the current version inside the caller's guarded transaction.

    The result is provisional until the outer transaction commits. Any failure
    must escape that transaction so all backup and current writes roll back.
    """
    locked.require_active()
    if reason not in {"remote_missing", "remote_recreated", "manual_reload"}:
        raise ValueError("Invalid backup reason")
    if locked._backup_result is not None:
        if locked._backup_result.reason != reason:
            raise TaskSyncConflict("Task was already transferred with another reason")
        previous = locked._backup_result
        return BackupTransferResult(
            previous.backup_id, previous.source_task_uuid, previous.source_generation,
            previous.reason, previous.detail_count, False,
        )
    task = locked.task
    if task is None:
        return BackupTransferResult(None, locked.expected.task_uuid, None, reason, 0, False)
    if (task.sendtask_uuid, task.local_generation_id, task.sync_revision) != (
        locked.expected.task_uuid, locked.expected.generation, locked.expected.revision,
    ):
        raise TaskSyncConflict("Backup must capture the expected current generation")
    session = locked.session
    if session.new or session.dirty or session.deleted:
        raise TaskSyncConflict("Backup must run before caller mutations")
    details = await locked.lock_details()
    stats = (await session.execute(
        select(SendLogStats).where(SendLogStats.sendtask_uuid == task.sendtask_uuid)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    existing = await session.scalar(select(TaskBackup.backup_id).where(
        TaskBackup.source_task_uuid == task.sendtask_uuid,
        TaskBackup.source_local_generation_id == task.local_generation_id,
    ))
    if existing is not None:
        raise TaskSyncConflict("Current generation already has a backup; refusing to discard data")
    template_uuids = {detail.template_uuid for detail in details if detail.template_uuid}
    template_uuids.update(task.mail_template or [])
    template_fields = [name for name in (
        "mtmpl_uuid", "mtmpl_name", "mtmpl_title", "mtmpl_tag", "mtmpl_mail_attached",
        "mtmpl_owner_gid", "mtmpl_create_ut", "mtmpl_update_ut", "mail_from",
        "mail_from_address", "weight_score",
    ) if name in Mtmpl.__table__.c]
    template_snapshots = {template_uuid: None for template_uuid in sorted(template_uuids)}
    if template_uuids:
        templates = (await session.execute(select(
            *(Mtmpl.__table__.c[name] for name in template_fields),
        ).where(Mtmpl.mtmpl_uuid.in_(sorted(template_uuids))))).mappings().all()
        for template in templates:
            template_snapshots[template["mtmpl_uuid"]] = dict(template)
    task_snapshot = {column.name: getattr(task, column.name) for column in SendTask.__table__.columns}
    stats_snapshot = None if stats is None else {
        column.name: getattr(stats, column.name) for column in SendLogStats.__table__.columns
    }
    backup_id = await session.scalar(insert(TaskBackup).values(
        source_task_uuid=task.sendtask_uuid,
        source_create_ut=task.sendtask_create_ut,
        source_local_generation_id=task.local_generation_id,
        sendtask_id=task.sendtask_id, owner_gids=list(task.sendtask_owner_gid),
        reason=reason, snapshot_schema_version=1,
        task_snapshot=_json_snapshot(task_snapshot), stats_snapshot=_json_snapshot(stats_snapshot),
        stats_snapshot_at=None, mail_template_snapshot=_json_snapshot(template_snapshots),
    ).returning(TaskBackup.backup_id))
    if details:
        await session.execute(insert(TaskBackupDetail), [{
            "backup_id": backup_id,
            **{column.name: getattr(detail, column.name) for column in SendLogDetail.__table__.columns if column.name != "id"},
        } for detail in details])
    await session.execute(delete(SendLogDetail).where(SendLogDetail.sendtask_uuid == task.sendtask_uuid))
    await session.execute(delete(SendLogStats).where(SendLogStats.sendtask_uuid == task.sendtask_uuid))
    await session.delete(task)
    await session.flush()
    result = BackupTransferResult(
        backup_id, task.sendtask_uuid, task.local_generation_id, reason, len(details), True,
    )
    locked.task = None
    locked._backup_result = result
    return result


def _sqlstate(error):
    original = error.orig
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


@asynccontextmanager
async def task_sync_transaction(session_factory, expected: ExpectedTaskVersion, *, lock_timeout_ms=5000):
    """Own a fresh transaction; callers must use its session and never commit it.

    Prepare remote data before entering. All future sync writers must use this
    guard; advisory locks cannot protect against legacy writers that ignore it.
    Successful retained generations advance once, including unchanged results.
    Replacement generations are created by the caller with a fresh ID/revision 0.
    """
    if type(lock_timeout_ms) is not int or not 1 <= lock_timeout_ms <= 60000:
        raise ValueError("lock_timeout_ms must be between 1 and 60000")
    try:
        async with session_factory() as session:
            async with session.begin():
                if await session.scalar(text("SHOW transaction_isolation")) != "read committed":
                    raise ValueError("Task sync requires READ COMMITTED isolation")
                await session.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {
                    "timeout": f"{lock_timeout_ms}ms",
                })
                await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {
                    "key": task_lock_key(expected.task_uuid),
                })
                task = (await session.execute(
                    select(SendTask).where(SendTask.sendtask_uuid == expected.task_uuid)
                    .with_for_update().execution_options(populate_existing=True)
                )).scalar_one_or_none()
                actual = (task.local_generation_id, task.sync_revision) if task else (None, None)
                if actual != (expected.generation, expected.revision):
                    raise TaskSyncConflict("Prepared task version is stale")
                locked = LockedTask(session, expected, task, _active=True)
                try:
                    yield locked
                finally:
                    locked._active = False
                if task is not None and task.sendtask_uuid != expected.task_uuid:
                    raise TaskSyncConflict("Task identity must not change inside apply")
                await session.flush()
                current = (await session.execute(select(
                    SendTask.local_generation_id, SendTask.sync_revision,
                ).where(SendTask.sendtask_uuid == expected.task_uuid))).one_or_none()
                if current is not None:
                    if current[0] == expected.generation:
                        if current[1] != expected.revision:
                            raise TaskSyncConflict("Caller must not change the retained revision")
                        await session.execute(update(SendTask).where(
                            SendTask.sendtask_uuid == expected.task_uuid,
                        ).values(sync_revision=expected.revision + 1))
                    elif current[1] != 0:
                        raise TaskSyncConflict("New generations must start at revision zero")
    except DBAPIError as error:
        if _sqlstate(error) == "55P03":
            raise TaskSyncLockTimeout("Task sync lock wait timed out") from None
        if _sqlstate(error) in {"40P01", "40001"}:
            raise TaskSyncConflict("Retry task sync after a transaction conflict") from None
        raise