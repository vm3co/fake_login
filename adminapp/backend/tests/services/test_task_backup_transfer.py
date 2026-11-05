import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update, func
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.repository.database import Base
from backend.repository.models import (
    CustomerAcct, CustomerTask, Mtmpl, SendTask, SendLogDetail, SendLogStats,
    TaskBackup, TaskBackupDetail,
)
from backend.tests.repository.test_task_backup_schema import schema_engine, set_path
from backend.tests.services.test_task_sync import wait_until_blocked
from backend.services.task_sync import (
    TaskSyncConflict, read_expected_task_version, task_sync_transaction,
    transfer_task_to_backup, _json_snapshot,
)


async def setup_transfer(schema_engine, *, details=True, stats=True):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(insert(SendTask).values(
            sendtask_uuid="task-1", sendtask_id="Original", sendtask_owner_gid=["org-1"],
            sendtask_create_ut=100, mail_template=["template-1", "missing"],
            mail_delivery={"nested": [1, None]},
        ))
        await conn.execute(insert(CustomerTask).values(customer_uuid="customer-1", sendtask_uuid="task-1"))
        await conn.execute(insert(CustomerAcct).values(
            customer_uuid="customer-1", customer_name="Customer", customer_full_name="Test Customer",
            password_hash="unused", acct_uuid="acct-1",
            sendtasks=[{"uuid": "task-1"}],
        ))
        await conn.execute(insert(Mtmpl).values(mtmpl_uuid="template-1", mtmpl_title="Original subject", mtmpl_tag=["tag-1"]))
        if stats:
            await conn.execute(insert(SendLogStats).values(sendtask_uuid="task-1", totalplanned=2, todayfailed=1))
        if details:
            for number in (1, 2):
                await conn.execute(insert(SendLogDetail).values(
                    uuid=f"old-log-{number}", sendtask_uuid="task-1", template_uuid="template-1",
                    target_email="same@example.test", person_info="Person", plan_time=100,
                    access_time=[10, 20], access_src=["ip-1", "ip-2"],
                    second_access_time=[30, 40], second_qrcode_time=[50, 60],
                    second_input_time=[70, 80], second_input_info=['{"one":1}', '{"two":2}'],
                ))
    return async_sessionmaker(engine, expire_on_commit=False), engine, schema


async def current_counts(factory):
    async with factory() as session:
        return tuple([await session.scalar(select(func.count()).select_from(model)) for model in (
            SendTask, SendLogDetail, SendLogStats, TaskBackup, TaskBackupDetail,
        )])


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["remote_missing", "remote_recreated", "manual_reload"])
async def test_complete_transfer_keeps_payload_relations_and_snapshot(schema_engine, reason):
    factory, engine, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with factory() as session:
        original_task = (await session.execute(select(SendTask.__table__))).mappings().one()
        original_stats = (await session.execute(select(SendLogStats.__table__))).mappings().one()
        originals = (await session.execute(select(SendLogDetail.__table__).order_by(SendLogDetail.uuid))).mappings().all()
    async with task_sync_transaction(factory, expected) as locked:
        result = await transfer_task_to_backup(locked, reason=reason)
        assert result.created and result.detail_count == 2
        repeated = await transfer_task_to_backup(locked, reason=reason)
        assert repeated.backup_id == result.backup_id and not repeated.created
        assert await current_counts(factory) == (1, 2, 1, 0, 0)
    assert await current_counts(factory) == (0, 0, 0, 1, 2)
    async with factory() as session:
        backup = (await session.execute(select(TaskBackup))).scalar_one()
        assert backup.task_snapshot == dict(original_task)
        assert backup.stats_snapshot == dict(original_stats)
        assert backup.stats_snapshot_at is None
        assert backup.owner_gids == ["org-1"]
        assert backup.reason == reason
        assert backup.source_local_generation_id == expected.generation
        assert backup.mail_template_snapshot["missing"] is None
        assert backup.mail_template_snapshot["template-1"]["mtmpl_title"] == "Original subject"
        rows = (await session.execute(select(TaskBackupDetail.__table__).order_by(TaskBackupDetail.uuid))).mappings().all()
        for original, copied in zip(originals, rows):
            assert {key: copied[key] for key in original if key != "id"} == {key: value for key, value in original.items() if key != "id"}
        assert await session.scalar(select(CustomerTask.customer_uuid)) == "customer-1"
        assert await session.scalar(select(CustomerAcct.sendtasks)) == [{"uuid": "task-1"}]
    async with engine.begin() as conn:
        await conn.execute(delete(Mtmpl))
    async with factory() as session:
        assert (await session.scalar(select(TaskBackup.mail_template_snapshot)))["template-1"]["mtmpl_title"] == "Original subject"
    missing = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, missing) as locked:
        assert not (await transfer_task_to_backup(locked, reason=reason)).created
    assert await current_counts(factory) == (0, 0, 0, 1, 2)
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected):
            pytest.fail("Committed source version cannot be moved twice")


@pytest.mark.asyncio
async def test_zero_details_and_unknown_stats_are_valid(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine, details=False, stats=False)
    async with task_sync_transaction(factory, await read_expected_task_version(factory, "task-1")) as locked:
        result = await transfer_task_to_backup(locked, reason="remote_missing")
        assert result.detail_count == 0
    async with factory() as session:
        backup = await session.scalar(select(TaskBackup))
        assert backup.stats_snapshot is None and backup.stats_snapshot_at is None
    assert await current_counts(factory) == (0, 0, 0, 1, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["detail", "delete"])
async def test_database_failure_rolls_back_whole_transfer(schema_engine, failure):
    factory, engine, schema = await setup_transfer(schema_engine)
    table = "task_backup_details" if failure == "detail" else "sendtasks"
    operation = "INSERT" if failure == "detail" else "DELETE"
    condition = "IF NEW.uuid = 'old-log-2' THEN RAISE EXCEPTION 'injected'; END IF;" if failure == "detail" else "RAISE EXCEPTION 'injected';"
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.execute(text(f"CREATE FUNCTION fail_transfer() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {condition} RETURN NEW; END $$"))
        await conn.execute(text(f"CREATE TRIGGER fail_transfer BEFORE {operation} ON {table} FOR EACH ROW EXECUTE FUNCTION fail_transfer()"))
    expected = await read_expected_task_version(factory, "task-1")
    with pytest.raises(DBAPIError):
        async with task_sync_transaction(factory, expected) as locked:
            await transfer_task_to_backup(locked, reason="remote_missing")
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    assert await read_expected_task_version(factory, "task-1") == expected
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.execute(text(f"DROP TRIGGER fail_transfer ON {table}"))
    async with task_sync_transaction(factory, expected) as locked:
        await transfer_task_to_backup(locked, reason="remote_missing")
    assert await current_counts(factory) == (0, 0, 0, 1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_later_failure_or_cancellation_restores_original(schema_engine, cancel):
    factory, _, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    error = asyncio.CancelledError if cancel else IntegrityError
    with pytest.raises(error):
        async with task_sync_transaction(factory, expected) as locked:
            await transfer_task_to_backup(locked, reason="remote_recreated")
            if cancel:
                raise asyncio.CancelledError()
            locked.session.add(SendTask(sendtask_uuid="task-1", sendtask_id="Bad", sendtask_owner_gid=None))
            await locked.session.flush()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    assert await read_expected_task_version(factory, "task-1") == expected


@pytest.mark.asyncio
async def test_replacement_and_late_old_event_do_not_modify_backup_or_new_version(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, expected) as locked:
        await transfer_task_to_backup(locked, reason="remote_recreated")
        locked.session.add(SendTask(sendtask_uuid="task-1", sendtask_id="New", sendtask_owner_gid=["org-2"], local_generation_id=str(uuid4())))
        await locked.session.flush()
        locked.session.add(SendLogDetail(uuid="new-log", sendtask_uuid="task-1", second_input_time=[]))
    async with factory() as session:
        async with session.begin():
            result = await session.execute(update(SendLogDetail).where(SendLogDetail.uuid == "old-log-1").values(second_input_time=[999]))
            assert result.rowcount == 0
        assert await session.scalar(select(SendTask.sendtask_id)) == "New"
        assert await session.scalar(select(SendLogDetail.second_input_time)) == []
        assert (await session.scalars(select(TaskBackupDetail.second_input_time))).all() == [[70, 80], [70, 80]]


@pytest.mark.asyncio
async def test_inflight_event_commits_before_locked_snapshot(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    pid_ready = asyncio.Future()

    async def move():
        async with engine.connect() as connection:
            pid_ready.set_result(await connection.scalar(text("SELECT pg_backend_pid()")))
            await connection.rollback()
            async with task_sync_transaction(async_sessionmaker(connection), expected) as locked:
                await transfer_task_to_backup(locked, reason="remote_missing")

    async with factory() as writer:
        async with writer.begin():
            await writer.execute(update(SendLogDetail).where(SendLogDetail.uuid == "old-log-1").values(second_access_time=[30, 40, 99]))
            pending = asyncio.create_task(move())
            await wait_until_blocked(engine, await pid_ready)
    await asyncio.wait_for(pending, 5)
    async with factory() as session:
        assert await session.scalar(select(TaskBackupDetail.second_access_time).where(TaskBackupDetail.uuid == "old-log-1")) == [30, 40, 99]


@pytest.mark.asyncio
async def test_existing_backup_conflict_never_deletes_current(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(
            source_task_uuid="task-1", source_local_generation_id=expected.generation,
            sendtask_id="Existing", owner_gids=[], reason="manual_reload", task_snapshot={},
        ))
    with pytest.raises(TaskSyncConflict):
        async with task_sync_transaction(factory, expected) as locked:
            await transfer_task_to_backup(locked, reason="remote_missing")
    assert await current_counts(factory) == (1, 2, 1, 1, 0)


@pytest.mark.asyncio
async def test_backup_guard_and_reason_validation(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, expected) as locked:
        with pytest.raises(ValueError):
            await transfer_task_to_backup(locked, reason="invalid")
    with pytest.raises(RuntimeError, match="inside"):
        await transfer_task_to_backup(locked, reason="remote_missing")
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_event_waiting_behind_transfer_cannot_append_to_history(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    pid_ready = asyncio.Future()

    async def event_writer():
        async with engine.connect() as connection:
            pid_ready.set_result(await connection.scalar(text("SELECT pg_backend_pid()")))
            await connection.rollback()
            async with connection.begin():
                result = await connection.execute(update(SendLogDetail).where(
                    SendLogDetail.uuid == "old-log-1",
                ).values(second_access_time=func.array_append(SendLogDetail.second_access_time, 999)))
                return result.rowcount

    async with task_sync_transaction(factory, expected) as locked:
        await locked.lock_details()
        pending = asyncio.create_task(event_writer())
        await wait_until_blocked(engine, await pid_ready)
        await transfer_task_to_backup(locked, reason="remote_missing")
        assert not pending.done()
    assert await asyncio.wait_for(pending, 5) == 0
    async with factory() as session:
        assert await session.scalar(select(TaskBackupDetail.second_access_time).where(
            TaskBackupDetail.uuid == "old-log-1",
        )) == [30, 40]


@pytest.mark.asyncio
async def test_transfer_preserves_other_task_and_rejects_caller_mutations(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(SendTask).values(
            sendtask_uuid="other-task", sendtask_id="Other", sendtask_owner_gid=["org-2"],
        ))
        await conn.execute(insert(SendLogDetail).values(uuid="other-log", sendtask_uuid="other-task"))
        await conn.execute(insert(SendLogStats).values(sendtask_uuid="other-task", totalplanned=1))
    expected = await read_expected_task_version(factory, "task-1")
    with pytest.raises(TaskSyncConflict, match="before caller mutations"):
        async with task_sync_transaction(factory, expected) as locked:
            locked.task.sendtask_id = "Modified before snapshot"
            await transfer_task_to_backup(locked, reason="manual_reload")
    assert await read_expected_task_version(factory, "task-1") == expected
    async with task_sync_transaction(factory, expected) as locked:
        await transfer_task_to_backup(locked, reason="remote_missing")
    assert await current_counts(factory) == (1, 1, 1, 1, 2)
    async with factory() as session:
        assert await session.scalar(select(SendTask.sendtask_uuid)) == "other-task"
        assert await session.scalar(select(SendLogDetail.uuid)) == "other-log"
        assert await session.scalar(select(SendLogStats.sendtask_uuid)) == "other-task"
        assert (await session.scalar(select(TaskBackup.task_snapshot)))["sendtask_id"] == "Original"


@pytest.mark.asyncio
async def test_repeated_transfer_with_different_reason_rolls_back(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    with pytest.raises(TaskSyncConflict, match="another reason"):
        async with task_sync_transaction(factory, expected) as locked:
            await transfer_task_to_backup(locked, reason="remote_missing")
            await transfer_task_to_backup(locked, reason="manual_reload")
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


def test_json_snapshot_is_strict_and_timezone_explicit():
    value = {"time": datetime(2026, 11, 5, tzinfo=timezone.utc), "nested": [None, True, 123]}
    assert _json_snapshot(value) == {"time": "2026-11-05T00:00:00+00:00", "nested": [None, True, 123]}
    for value in (datetime(2026, 11, 5), float("nan"), object()):
        with pytest.raises((ValueError, TypeError)):
            _json_snapshot(value)