import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.repository.models import SendTask, SendLogDetail
from backend.tests.repository.test_task_backup_schema import schema_engine
from backend.services.task_sync import (
    ExpectedTaskVersion, TaskSyncConflict, TaskSyncLockTimeout,
    read_expected_task_version, task_lock_key, task_sync_transaction,
)


async def setup_sessions(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: SendTask.__table__.create(sync))
        await conn.run_sync(lambda sync: SendLogDetail.__table__.create(sync))
        await conn.execute(insert(SendTask).values(
            sendtask_uuid="task-1", sendtask_id="Original", sendtask_owner_gid=["org-1"],
        ))
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def wait_until_blocked(engine, pid):
    async def observe():
        async with engine.connect() as conn:
            while True:
                blocked = await conn.scalar(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid})
                if blocked:
                    return
    await asyncio.wait_for(observe(), 5)


def test_lock_key_is_stable_namespaced_and_signed_bigint():
    assert task_lock_key("task-1") == task_lock_key("task-1")
    assert task_lock_key("task-1") != task_lock_key("task-2")
    assert -(2**63) <= task_lock_key("task-1") < 2**63
    for seed in ("1", "42"):
        value = subprocess.check_output([
            sys.executable, "-c",
            "from backend.services.task_sync import task_lock_key; print(task_lock_key('task-1'))",
        ], env={**os.environ, "PYTHONHASHSEED": seed}, text=True)
        assert int(value.strip()) == task_lock_key("task-1")


@pytest.mark.parametrize("uuid,generation,revision", [
    ("", None, None), ("task-1", None, 1), ("task-1", "gen", None),
    ("task-1", "", 0), ("task-1", "gen", -1), ("task-1", "gen", True),
])
def test_invalid_expected_version_is_rejected(uuid, generation, revision):
    with pytest.raises(ValueError):
        ExpectedTaskVersion(uuid, generation, revision)


@pytest.mark.asyncio
async def test_commits_once_and_rejects_stale_revision(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, expected) as locked:
        locked.task.sendtask_id = "Updated"
    current = await read_expected_task_version(factory, "task-1")
    assert current.generation == expected.generation
    assert current.revision == expected.revision + 1
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected):
            pytest.fail("Stale data must not enter apply")
    assert await read_expected_task_version(factory, "task-1") == current


@pytest.mark.asyncio
async def test_old_missing_result_cannot_touch_replacement(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    old = await read_expected_task_version(factory, "task-1")
    replacement = str(uuid4())
    async with task_sync_transaction(factory, old) as locked:
        locked.task.local_generation_id = replacement
        locked.task.sync_revision = 0
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, old):
            pytest.fail("Old 404 must not enter apply")
    assert (await read_expected_task_version(factory, "task-1")).generation == replacement


@pytest.mark.asyncio
async def test_same_uuid_waits_and_different_uuid_proceeds(schema_engine):
    factory, engine = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    pid_ready = asyncio.Future()

    async def second():
        async with engine.connect() as connection:
            pid_ready.set_result(await connection.scalar(text("SELECT pg_backend_pid()")))
            await connection.rollback()
            async with task_sync_transaction(async_sessionmaker(connection), expected):
                pytest.fail("Second prepared result must be stale after first commits")

    async with task_sync_transaction(factory, expected):
        pending = asyncio.create_task(second())
        pid = await pid_ready
        await wait_until_blocked(engine, pid)
        other = await read_expected_task_version(factory, "other-task")
        async with asyncio.timeout(2):
            async with task_sync_transaction(factory, other):
                pass
        assert not pending.done()
    with pytest.raises(TaskSyncConflict):
        await asyncio.wait_for(pending, 5)


@pytest.mark.asyncio
async def test_absent_uuid_is_locked_and_only_one_import_passes(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "new-task")
    assert expected == ExpectedTaskVersion("new-task", None, None)
    async with task_sync_transaction(factory, expected) as first:
        with pytest.raises(TaskSyncLockTimeout):
            async with task_sync_transaction(factory, expected, lock_timeout_ms=50):
                pytest.fail("Absent UUID must still be locked")
        first.session.add(SendTask(sendtask_uuid="new-task", sendtask_id="New", sendtask_owner_gid=[]))
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected):
            pytest.fail("Second importer must prepare again")
    assert (await read_expected_task_version(factory, "new-task")).revision == 0


@pytest.mark.asyncio
async def test_exception_and_cancellation_roll_back_and_release_lock(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    for failure in (RuntimeError, asyncio.CancelledError):
        with pytest.raises(failure):
            async with task_sync_transaction(factory, expected) as locked:
                locked.task.sendtask_id = "Must rollback"
                await locked.session.flush()
                raise failure()
        assert await read_expected_task_version(factory, "task-1") == expected
        async with factory() as session:
            assert await session.scalar(select(SendTask.sendtask_id)) == "Original"
    async with task_sync_transaction(factory, expected, lock_timeout_ms=100):
        pass


@pytest.mark.asyncio
async def test_cancelling_blocked_waiter_does_not_leak_lock(schema_engine):
    factory, engine = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    pid_ready = asyncio.Future()

    async def waiter():
        async with engine.connect() as connection:
            pid_ready.set_result(await connection.scalar(text("SELECT pg_backend_pid()")))
            await connection.rollback()
            async with task_sync_transaction(async_sessionmaker(connection), expected):
                pytest.fail("Waiter should be cancelled")

    async with task_sync_transaction(factory, expected):
        pending = asyncio.create_task(waiter())
        await wait_until_blocked(engine, await pid_ready)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 5)
    current = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, current, lock_timeout_ms=100):
        pass


@pytest.mark.asyncio
async def test_details_lock_timeout_rolls_back_and_can_retry(schema_engine):
    factory, engine = await setup_sessions(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(SendLogDetail).values(uuid="log-1", sendtask_uuid="task-1", second_access_time=[1, 2]))
    expected = await read_expected_task_version(factory, "task-1")
    async with factory() as writer:
        async with writer.begin():
            await writer.execute(update(SendLogDetail).values(second_access_time=[1, 2, 3]))
            with pytest.raises(TaskSyncLockTimeout):
                async with task_sync_transaction(factory, expected, lock_timeout_ms=50) as locked:
                    await locked.lock_details()
    assert await read_expected_task_version(factory, "task-1") == expected
    async with task_sync_transaction(factory, expected) as locked:
        details = await locked.lock_details()
        assert details[0].second_access_time == [1, 2, 3]


@pytest.mark.asyncio
async def test_manual_revision_change_is_rejected_and_rolled_back(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected) as locked:
            locked.task.sync_revision = 99
    assert await read_expected_task_version(factory, "task-1") == expected


@pytest.mark.asyncio
async def test_row_lock_timeout_is_retryable_without_changing_data(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with factory() as writer:
        async with writer.begin():
            await writer.execute(select(SendTask).with_for_update())
            with pytest.raises(TaskSyncLockTimeout) as error:
                async with task_sync_transaction(factory, expected, lock_timeout_ms=50):
                    pytest.fail("Task row lock should time out")
            assert error.value.retryable is True
    assert await read_expected_task_version(factory, "task-1") == expected
    async with task_sync_transaction(factory, expected, lock_timeout_ms=100):
        pass


@pytest.mark.asyncio
async def test_removed_task_rejects_prepared_existing_version(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, expected) as locked:
        await locked.session.delete(locked.task)
    assert await read_expected_task_version(factory, "task-1") == ExpectedTaskVersion("task-1", None, None)
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected):
            pytest.fail("Removed task must invalidate old successful reads")


@pytest.mark.asyncio
async def test_new_generation_requires_initial_revision_zero(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected) as locked:
            locked.task.local_generation_id = str(uuid4())
            locked.task.sync_revision = 5
    assert await read_expected_task_version(factory, "task-1") == expected


@pytest.mark.asyncio
async def test_task_uuid_cannot_be_renamed_by_apply(schema_engine):
    factory, _ = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected) as locked:
            locked.task.sendtask_uuid = "other-task"
    assert await read_expected_task_version(factory, "task-1") == expected


@pytest.mark.asyncio
async def test_same_uuid_waiter_can_proceed_after_owner_rolls_back(schema_engine):
    factory, engine = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    pid_ready = asyncio.Future()

    async def second():
        async with engine.connect() as connection:
            pid_ready.set_result(await connection.scalar(text("SELECT pg_backend_pid()")))
            await connection.rollback()
            async with task_sync_transaction(async_sessionmaker(connection), expected) as locked:
                locked.task.sendtask_id = "After rollback"

    with pytest.raises(RuntimeError, match="rollback owner"):
        async with task_sync_transaction(factory, expected):
            pending = asyncio.create_task(second())
            await wait_until_blocked(engine, await pid_ready)
            raise RuntimeError("rollback owner")
    await asyncio.wait_for(pending, 5)
    assert (await read_expected_task_version(factory, "task-1")).revision == 1


@pytest.mark.asyncio
async def test_repeatable_read_is_rejected_before_apply(schema_engine):
    factory, engine = await setup_sessions(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    repeatable = engine.execution_options(isolation_level="REPEATABLE READ")
    with pytest.raises(ValueError, match="READ COMMITTED"):
        async with task_sync_transaction(async_sessionmaker(repeatable), expected):
            pytest.fail("Snapshot isolation can hide commits made while waiting")


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, -1, 60001, True, "100"])
async def test_invalid_timeout_fails_without_opening_session(timeout):
    def no_session():
        pytest.fail("Invalid timeout must not connect")

    with pytest.raises(ValueError):
        async with task_sync_transaction(no_session, ExpectedTaskVersion("task-1", None, None), lock_timeout_ms=timeout):
            pass