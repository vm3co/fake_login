import asyncio
from dataclasses import replace

import pytest
from unittest.mock import AsyncMock
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from backend.repository.task_reload_schema import migrate_task_reload_schema, task_reload_operations
from backend.tests.repository.test_task_backup_schema import schema_engine, set_path
from backend.repository.models import SendTask, SendLogDetail, TaskBackup, TaskBackupDetail
from backend.services.task_sync_core import TaskSyncService, TaskReloadIntent, TaskSyncAccessDenied
from backend.services.task_sync import TaskSyncConflict
from backend.services.se2_task_reader import TaskNotFound, TaskReadError
from backend.tests.services.test_task_backup_transfer import setup_transfer, current_counts
from backend.tests.services.test_task_sync_core import snapshot
from types import SimpleNamespace
from unittest.mock import patch


@pytest.mark.asyncio
async def test_reload_migration_is_repeatable_and_operation_identity_is_unique(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await migrate_task_reload_schema(conn)
        await migrate_task_reload_schema(conn)
        values = {
            "operation_id": "job-1", "task_uuid": "task-1", "actor": "user-a",
            "owner_gids": ["org-1"], "source_generation": "generation-1",
            "result": {"status": "reloaded", "committed": True},
        }
        await conn.execute(insert(task_reload_operations).values(**values))
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(insert(task_reload_operations).values(**values))
        await conn.execute(insert(task_reload_operations).values(**{**values, "operation_id": "job-2"}))
        assert len((await conn.execute(select(task_reload_operations))).all()) == 2


@pytest.mark.asyncio
async def test_same_version_reload_cleans_details_and_retry_replays_commit(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        source = (await conn.execute(select(SendTask.local_generation_id))).scalar_one()
        await conn.execute(insert(SendLogDetail).values(uuid="duplicate-old", sendtask_uuid="task-1", target_email="same@example.test"))
    reader = AsyncMock(read_task_snapshot=AsyncMock(return_value=snapshot(100, 2)))
    core = TaskSyncService(factory, reader)
    intent = TaskReloadIntent("job-1", "user-a", source)
    first = await core.sync("task-1", orgs=["org-1"], reload_intent=intent)
    assert first.status == "reloaded" and first.generation != source and first.source_generation == source
    assert first.backup_id and first.actor == "user-a" and first.committed and not first.replayed
    assert first.source_revision == 0 and first.revision == 0
    assert await current_counts(factory) == (1, 2, 1, 1, 3)
    async with factory() as session:
        backup = await session.scalar(select(TaskBackup))
        assert backup.reason == "manual_reload" and backup.recreated_detected_at is None
        assert (await session.scalars(select(SendLogDetail.second_input_time))).all() == [None, None]
        history = (await session.scalars(select(TaskBackupDetail.second_input_time).where(
            TaskBackupDetail.uuid != "duplicate-old",
        ))).all()
        assert history == [[70, 80], [70, 80]]
        assert len((await session.scalars(select(TaskBackupDetail))).all()) == 3
    reader.read_task_snapshot.side_effect = RuntimeError("remote unavailable on retry")
    retry = await core.sync("task-1", orgs=["org-1"], reload_intent=intent)
    assert retry.replayed and retry.backup_id == first.backup_id
    assert await current_counts(factory) == (1, 2, 1, 1, 3)
    reader.read_task_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_reload_job_admission_queues_only_authorized_current_tasks(async_client):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    rows = [SimpleNamespace(sendtask_uuid=task_uuid, sendtask_id=task_uuid, sendtask_owner_gid=orgs, local_generation_id="generation-1")
            for task_uuid, orgs in (("allowed", ["org-1"]), ("denied", ["org-2"]))]
    start = AsyncMock(return_value={"job_id": "job-1", "accepted": [], "excluded": []})
    core = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "username": "user-a", "orgs": ["org-1"]}
    try:
        with patch.object(job_api.db_controller, "get", AsyncMock(return_value=rows)), \
             patch.object(job_api.job_manager, "start_job", start), \
             patch.object(job_api.db_user, "get_task_sync", return_value=core):
            response = await async_client.post("/api/jobs/start", json={
                "job_type": "force_reload_sendtask", "params": {"confirm_reload": True, "uuids": ["allowed", "allowed", "denied"], "orgs": ["org-2"]},
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200, response.text
    assert start.await_args.kwargs["items"] == [{"sendtask_uuid": "allowed", "sendtask_id": "allowed"}]
    assert start.await_args.kwargs["job_code"] == "force_reload_sendtask"
    assert start.await_args.kwargs["request_params"]["source_generations"] == {"allowed": "generation-1"}
    core.sync.assert_not_awaited()


async def reload_setup(schema_engine, *, value=None, error=None):
    factory, engine, schema = await setup_transfer(schema_engine)
    async with factory() as session:
        generation = await session.scalar(select(SendTask.local_generation_id))
    reader = AsyncMock(read_task_snapshot=AsyncMock(return_value=value or snapshot(), side_effect=error))
    return TaskSyncService(factory, reader), factory, engine, schema, TaskReloadIntent("job-1", "user-a", generation)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 5])
async def test_reload_accepts_complete_zero_or_multiple_same_email_templates(schema_engine, count):
    value = snapshot(100, count)
    for number, record in enumerate(value.sendlogs):
        record["template_uuid"] = f"template-{number % 2}"
    core, factory, _, _, intent = await reload_setup(schema_engine, value=value)
    result = await core.sync("task-1", orgs=None, reload_intent=intent)
    assert result.status == "reloaded"
    assert await current_counts(factory) == (1, count, 1, 1, 2)
    async with factory() as session:
        assert (await session.scalars(select(SendLogDetail.target_email))).all() == ["same@example.test"] * count


@pytest.mark.asyncio
async def test_deliberate_second_reload_creates_new_generation_and_backup(schema_engine):
    core, factory, _, _, intent = await reload_setup(schema_engine)
    first = await core.sync("task-1", orgs=None, reload_intent=intent)
    second = await core.sync("task-1", orgs=None, reload_intent=TaskReloadIntent("job-2", "user-a", first.generation))
    assert second.status == "reloaded" and first.generation != second.generation
    assert second.backup_id != first.backup_id
    assert await current_counts(factory) == (1, 2, 1, 2, 4)
    retry = await core.sync("task-1", orgs=None, reload_intent=intent)
    assert retry.replayed and retry.generation == first.generation
    async with factory() as session:
        assert await session.scalar(select(SendTask.local_generation_id)) == second.generation


@pytest.mark.asyncio
async def test_retry_after_backup_deleted_does_not_touch_current(schema_engine):
    core, factory, engine, _, intent = await reload_setup(schema_engine)
    result = await core.sync("task-1", orgs=None, reload_intent=intent)
    async with engine.begin() as conn:
        await conn.execute(delete(TaskBackup).where(TaskBackup.backup_id == result.backup_id))
    retry = await core.sync("task-1", orgs=None, reload_intent=intent)
    assert retry.replayed and retry.backup_id == result.backup_id
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TaskReadError("incomplete_pages"), TaskReadError("http_error"), asyncio.CancelledError()])
async def test_remote_failure_or_cancel_never_clears_current(schema_engine, error):
    core, factory, _, _, intent = await reload_setup(schema_engine, error=error)
    with pytest.raises(type(error)):
        await core.sync("task-1", orgs=None, reload_intent=intent)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    async with factory() as session:
        assert (await session.execute(select(task_reload_operations))).all() == []


@pytest.mark.asyncio
async def test_confirmed_missing_backs_up_without_claiming_reload(schema_engine):
    core, factory, _, _, intent = await reload_setup(schema_engine, error=TaskNotFound("missing"))
    result = await core.sync("task-1", orgs=["org-1"], reload_intent=intent)
    assert result.status == "backed_up" and result.generation is None
    async with factory() as session:
        assert (await session.scalar(select(TaskBackup))).reason == "remote_missing"
    assert (await core.sync("task-1", orgs=["org-1"], reload_intent=intent)).replayed
    assert await current_counts(factory) == (0, 0, 0, 1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["send_log_details", "sendlog_stats", "task_reload_operations"])
async def test_any_write_failure_rolls_back_backup_replacement_and_receipt(schema_engine, table):
    core, factory, engine, schema, intent = await reload_setup(schema_engine)
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.execute(text("CREATE FUNCTION fail_reload() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'reload injected'; END $$"))
        await conn.execute(text(f"CREATE TRIGGER fail_reload BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION fail_reload()"))
    with pytest.raises(Exception, match="reload injected"):
        await core.sync("task-1", orgs=None, reload_intent=intent)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    async with factory() as session:
        assert await session.scalar(select(SendTask.local_generation_id)) == intent.source_generation
        assert (await session.execute(select(task_reload_operations))).all() == []


@pytest.mark.asyncio
async def test_cancel_in_transaction_rolls_back_all_changes(schema_engine):
    core, factory, _, _, intent = await reload_setup(schema_engine)

    def cancel(records):
        raise asyncio.CancelledError

    core.stats_calculator = cancel
    with pytest.raises(asyncio.CancelledError):
        await core.sync("task-1", orgs=None, reload_intent=intent)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_same_prepared_operation_concurrently_commits_only_once(schema_engine):
    core, factory, _, _, intent = await reload_setup(schema_engine)
    prepared = await core.prepare("task-1", orgs=["org-1"], reload_intent=intent)
    first, second = await asyncio.gather(core.apply(prepared), core.apply(prepared))
    assert first.backup_id == second.backup_id and first.generation == second.generation
    assert sum(result.replayed for result in (first, second)) == 1
    assert await current_counts(factory) == (1, 2, 1, 1, 2)


@pytest.mark.asyncio
async def test_stale_work_does_not_reload_newer_generation(schema_engine):
    core, factory, _, _, intent = await reload_setup(schema_engine)
    prepared = await core.prepare("task-1", orgs=None, reload_intent=intent)
    core.reader.read_task_snapshot.return_value = snapshot(200, 5)
    await core.sync("task-1", orgs=None)
    with pytest.raises(TaskSyncConflict):
        await core.apply(prepared)
    with pytest.raises(TaskSyncConflict):
        await core.sync("task-1", orgs=None, reload_intent=intent)
    assert await current_counts(factory) == (1, 5, 1, 1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [[], ["org-2"]])
async def test_unauthorized_prepare_never_reads_remote(schema_engine, scope):
    core, factory, _, _, intent = await reload_setup(schema_engine)
    with pytest.raises(TaskSyncAccessDenied):
        await core.sync("task-1", orgs=scope, reload_intent=intent)
    core.reader.read_task_snapshot.assert_not_awaited()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_receipt_requires_same_actor_source_and_authorized_org(schema_engine):
    core, _, _, _, intent = await reload_setup(schema_engine)
    await core.sync("task-1", orgs=None, reload_intent=intent)
    for wrong in (replace(intent, actor="other"), replace(intent, source_generation="other")):
        with pytest.raises(TaskSyncConflict):
            await core.sync("task-1", orgs=None, reload_intent=wrong)
    with pytest.raises(TaskSyncAccessDenied):
        await core.sync("task-1", orgs=["org-2"], reload_intent=intent)


@pytest.mark.asyncio
async def test_invalid_local_create_time_can_be_explicitly_repaired(schema_engine):
    core, factory, engine, _, intent = await reload_setup(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(sendtask_create_ut=None))
    assert (await core.sync("task-1", orgs=None, reload_intent=intent)).status == "reloaded"
    assert await current_counts(factory) == (1, 2, 1, 1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [
    {"uuids": ["task-1"]}, {"confirm_reload": "true", "uuids": ["task-1"]},
    {"confirm_reload": 1, "uuids": ["task-1"]},
    {"confirm_reload": True}, {"confirm_reload": True, "uuids": []},
    {"confirm_reload": True, "uuids": "task-1"}, {"confirm_reload": True, "uuids": [""]},
    {"confirm_reload": True, "uuids": [123]}, {"confirm_reload": True, "uuids": ["x" * 37]},
    {"confirm_reload": True, "uuids": ["task-1"], "backup_id": "backup-1"},
    {"confirm_reload": True, "uuids": ["task-1"], "backup_ids": ["backup-1"]},
])
async def test_job_rejects_unconfirmed_or_non_explicit_targets(async_client, params):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    start = AsyncMock()
    read = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "username": "user-a", "orgs": ["org-1"]}
    try:
        with patch.object(job_api.job_manager, "start_job", start), patch.object(job_api.db_controller, "get", read):
            response = await async_client.post("/api/jobs/start", json={"job_type": "force_reload_sendtask", "params": params})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 400, response.text
    start.assert_not_awaited()
    read.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [
    {"user_type": "customer", "username": "customer-a"},
    {"user_type": "user", "username": "user-a", "orgs": []},
    {"user_type": "user", "username": "user-a", "orgs": ["org-2"]},
])
async def test_job_rejects_customer_empty_scope_or_no_authorized_current(async_client, identity):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    start = AsyncMock()
    rows = [SimpleNamespace(sendtask_uuid="task-1", sendtask_id="Original", sendtask_owner_gid=["org-1"], local_generation_id="source")]
    app.dependency_overrides[get_current_user] = lambda: identity
    try:
        with patch.object(job_api.job_manager, "start_job", start), patch.object(job_api.db_controller, "get", AsyncMock(return_value=rows)):
            response = await async_client.post("/api/jobs/start", json={
                "job_type": "force_reload_sendtask", "params": {"confirm_reload": True, "uuids": ["task-1"]},
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 403, response.text
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_execution_and_retry_use_same_id_and_ignore_forged_actor(async_client, schema_engine):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app
    from backend.services.db_user import DBUser

    core, factory, _, _, intent = await reload_setup(schema_engine)
    rows = [SimpleNamespace(sendtask_uuid="task-1", sendtask_id="Original", sendtask_owner_gid=["org-1"], local_generation_id=intent.source_generation)]
    captured = {}

    async def start_job(username, name, task_func, **kwargs):
        captured["first"] = await task_func(accepted_items=kwargs["items"], job_id="queued-job")
        core.reader.read_task_snapshot.side_effect = RuntimeError("remote unavailable")
        captured["retry"] = await task_func(accepted_items=kwargs["items"], job_id="queued-job")
        return {"job_id": "queued-job", "accepted": kwargs["items"], "excluded": []}

    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "username": "user-a", "orgs": ["org-1"]}
    try:
        with patch.object(job_api, "db_user", DBUser(task_sync=core)), \
             patch.object(job_api.db_controller, "get", AsyncMock(return_value=rows)), \
             patch.object(job_api.job_manager, "mark_item", AsyncMock()), \
             patch.object(job_api.job_manager, "start_job", start_job):
            response = await async_client.post("/api/jobs/start", json={
                "job_type": "force_reload_sendtask", "params": {
                    "confirm_reload": True, "uuids": ["task-1"], "actor": "forged", "source_generations": {"task-1": "forged"},
                },
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200, response.text
    assert captured["first"]["reloaded_count"] == 1 and captured["first"]["job_status"] == "completed"
    audit = captured["first"]["reload_results"][0]
    assert audit["actor"] == "user-a" and audit["operation_id"] == "queued-job"
    assert audit["source_generation"] == intent.source_generation and audit["backup_id"]
    assert captured["retry"]["reload_results"][0]["replayed"]
    assert await current_counts(factory) == (1, 2, 1, 1, 2)


@pytest.mark.asyncio
async def test_reload_job_keeps_partial_and_cancelled_commits():
    from backend.api import job_api
    from backend.services.db_user import DBUser
    from backend.services.task_sync_core import TaskSyncResult
    from backend.services.task_sync_entrypoints import TaskSyncCancelled

    committed = TaskSyncResult("reloaded", "first", "new", 0, "backup", True, ("first",), True,
                               source_generation="old", operation_id="job-1", actor="user-a")
    core = AsyncMock()
    core.sync.side_effect = [committed, RuntimeError("incomplete_pages")]
    items = [{"sendtask_uuid": "first"}, {"sendtask_uuid": "second"}]
    with patch.object(job_api, "db_user", DBUser(task_sync=core)), patch.object(job_api.job_manager, "mark_item", AsyncMock()):
        result = await job_api.reload_job_items(items, "job-1", orgs=["org-1"], actor="user-a", generations={"first": "old", "second": "old-2"})
        assert result["job_status"] == "partial" and result["reloaded_count"] == result["failed_count"] == 1
        core.sync.side_effect = [committed, asyncio.CancelledError]
        with pytest.raises(TaskSyncCancelled) as error:
            await job_api.reload_job_items(items, "job-1", orgs=["org-1"], actor="user-a", generations={"first": "old", "second": "old-2"})
    assert error.value.results.results["first"].committed


@pytest.mark.asyncio
async def test_committed_reload_is_not_lost_when_item_reporting_fails(schema_engine):
    from backend.api import job_api
    from backend.services.db_user import DBUser

    core, factory, _, _, intent = await reload_setup(schema_engine)
    items = [{"sendtask_uuid": "task-1"}]
    with patch.object(job_api, "db_user", DBUser(task_sync=core)), \
         patch.object(job_api.job_manager, "mark_item", AsyncMock(side_effect=RuntimeError("report unavailable"))):
        result = await job_api.reload_job_items(items, "job-1", orgs=["org-1"], actor="user-a", generations={"task-1": intent.source_generation})
    assert result["job_status"] == "completed" and result["reloaded_count"] == 1
    assert result["notification_errors"]["task-1"] == "report unavailable"
    assert await current_counts(factory) == (1, 2, 1, 1, 2)


@pytest.mark.asyncio
async def test_reload_migration_failure_rolls_back_table_and_marker(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        with pytest.raises(RuntimeError, match="injected migration"):
            async with conn.begin_nested():
                with patch.object(type(conn), "run_sync", side_effect=RuntimeError("injected migration")):
                    await migrate_task_reload_schema(conn)
        assert await conn.scalar(text("SELECT to_regclass('task_reload_operations')")) is None
        await migrate_task_reload_schema(conn)
        assert await conn.scalar(text("SELECT count(*) FROM schema_migrations")) == 1


@pytest.mark.asyncio
async def test_apply_rechecks_current_organization_and_stale_revision(schema_engine):
    core, factory, engine, _, intent = await reload_setup(schema_engine)
    prepared = await core.prepare("task-1", orgs=["org-1"], reload_intent=intent)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(sendtask_owner_gid=["org-2"]))
    with pytest.raises(TaskSyncAccessDenied):
        await core.apply(prepared)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(sendtask_owner_gid=["org-1"], sync_revision=1))
    with pytest.raises(TaskSyncConflict):
        await core.apply(prepared)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_remote_organization_change_preserves_old_data(schema_engine):
    core, factory, _, _, intent = await reload_setup(schema_engine, value=snapshot(orgs=["org-2"]))
    with pytest.raises(TaskSyncAccessDenied):
        await core.sync("task-1", orgs=["org-1"], reload_intent=intent)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_same_detail_id_event_after_reload_only_changes_current(schema_engine):
    core, factory, engine, _, intent = await reload_setup(schema_engine)
    await core.sync("task-1", orgs=None, reload_intent=intent)
    async with engine.begin() as conn:
        await conn.execute(update(SendLogDetail).where(SendLogDetail.uuid == "old-log-1").values(second_input_time=[999]))
    async with factory() as session:
        assert await session.scalar(select(SendLogDetail.second_input_time).where(SendLogDetail.uuid == "old-log-1")) == [999]
        assert await session.scalar(select(TaskBackupDetail.second_input_time).where(TaskBackupDetail.uuid == "old-log-1")) == [70, 80]