from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import blake2b

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repository.models import SendLogDetail, SendTask


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

    async def lock_details(self) -> list[SendLogDetail]:
        """Call after the task lock and before copying the backup snapshot."""
        return list((await self.session.execute(
            select(SendLogDetail)
            .where(SendLogDetail.sendtask_uuid == self.expected.task_uuid)
            .order_by(SendLogDetail.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalars().all())


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
                yield LockedTask(session, expected, task)
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