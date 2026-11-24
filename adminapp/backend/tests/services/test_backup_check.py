from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from backend.repository.models import TaskBackup
from backend.services.backup_observation import update_backup_observations
from backend.tests.repository.test_task_backup_schema import schema_engine, backup_values
from backend.tests.services.test_task_backup_transfer import setup_transfer
from backend.services.backup_check import BackupCheckService, BackupCheckCancelled
from unittest.mock import AsyncMock
from backend.services.se2_task_reader import TaskReadError
from backend.tests.services.test_task_sync_core import snapshot
from fastapi import HTTPException
from unittest.mock import patch
import asyncio
from backend.services.se2_task_reader import TaskNotFound
from backend.services.task_sync_progress import TaskSyncProgress, track_task_sync
from sqlalchemy import update, text
from backend.services.task_sync import read_expected_task_version, task_sync_transaction, transfer_task_to_backup
from backend.tests.services.test_task_backup_transfer import current_counts


@pytest.mark.asyncio
async def test_observations_keep_evidence_reject_stale_and_never_mutate_snapshot(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old")).returning(TaskBackup.backup_id))
    start = datetime.now(timezone.utc)
    async with factory() as session:
        async with session.begin():
            await update_backup_observations(session, task_uuid="task-1", scope=["org-1"], checked_at=start, status="present", create_ut=200)
    for offset, status in ((1, "missing"), (2, "error"), (-1, "present")):
        async with factory() as session:
            async with session.begin():
                await update_backup_observations(session, task_uuid="task-1", scope=["org-1"],
                    checked_at=start + timedelta(seconds=offset), status=status, create_ut=100 if status == "present" else None)
    async with factory() as session:
        backup = await session.get(TaskBackup, backup_id)
        assert backup.latest_remote_status == "error" and backup.last_remote_create_ut is None
        assert backup.recreated_detected_at == start
        assert backup.task_snapshot == backup_values("old")["task_snapshot"]
        assert backup.source_create_ut == 100


@pytest.mark.asyncio
async def test_check_deduplicates_source_and_compares_each_authorized_version(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        ids = []
        for generation, created, org in (("one", 100, "org-1"), ("two", 200, "org-1"), ("other", 50, "org-2")):
            ids.append(await conn.scalar(insert(TaskBackup).values(**backup_values(generation, source_create_ut=created,
                owner_gids=[org])).returning(TaskBackup.backup_id)))
    value = snapshot(200)
    reader = AsyncMock(read_sendtask=AsyncMock(return_value={"data": value.task, "metadata": value.metadata}))
    result = await BackupCheckService(factory, reader).check(ids[:2], scope=["org-1"])
    assert result["checked_count"] == 2 and result["backups_changed"] and result["changed_uuids"] == []
    reader.read_sendtask.assert_awaited_once()
    async with factory() as session:
        backups = (await session.scalars(select(TaskBackup).order_by(TaskBackup.source_create_ut))).all()
        assert backups[0].latest_remote_status == "unchecked"
        assert backups[1].recreated_detected_at is not None
        assert backups[2].recreated_detected_at is None
    reader.read_sendtask.reset_mock()
    with pytest.raises(HTTPException):
        await BackupCheckService(factory, reader).check(ids, scope=["org-1"])
    reader.read_sendtask.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [(TaskNotFound("missing"), "missing"), (TaskReadError("http_error"), "error")])
async def test_remote_missing_or_error_keeps_prior_evidence(schema_engine, error, status):
    factory, engine, _ = await setup_transfer(schema_engine)
    evidence = datetime.now(timezone.utc) - timedelta(days=1)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old", recreated_detected_at=evidence)).returning(TaskBackup.backup_id))
    reader = AsyncMock(read_sendtask=AsyncMock(side_effect=error))
    result = await BackupCheckService(factory, reader).check([backup_id], scope=["org-1"])
    assert result["backup_observations"][0]["latest_remote_status"] == status
    async with factory() as session:
        assert (await session.get(TaskBackup, backup_id)).recreated_detected_at == evidence


@pytest.mark.asyncio
async def test_cancel_after_first_source_keeps_saved_observation(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        ids = [await conn.scalar(insert(TaskBackup).values(**backup_values(str(number), source_task_uuid=f"task-{number}")).returning(TaskBackup.backup_id)) for number in (1, 2)]
    reader = AsyncMock(read_sendtask=AsyncMock(side_effect=[{"data": snapshot(200).task}, asyncio.CancelledError]))
    save = AsyncMock()
    progress = TaskSyncProgress(save)
    with track_task_sync(progress):
        with pytest.raises(BackupCheckCancelled) as exc:
            await BackupCheckService(factory, reader).check(ids, scope=["org-1"])
    assert exc.value.results["checked_count"] == 1
    assert progress.result["backups_changed"] and len(progress.result["changed_backup_ids"]) == 1
    assert progress.result["changed_uuids"] == []
    assert save.await_count == 1


@pytest.mark.asyncio
async def test_job_strict_selection_queues_without_remote_read(async_client, schema_engine):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app
    from types import SimpleNamespace

    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old")).returning(TaskBackup.backup_id))
    reader = AsyncMock()
    start = AsyncMock(return_value={"job_id": "job", "accepted": [], "excluded": []})
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "username": "user-a", "orgs": ["org-1"]}
    try:
        with patch.object(job_api.db_user, "get_task_sync", return_value=SimpleNamespace(session_factory=factory, reader=reader)), \
             patch.object(job_api.job_manager, "start_job", start):
            response = await async_client.post("/api/jobs/start", json={"job_type": "check_backup_recreated", "params": {"backup_ids": [backup_id, backup_id]}})
            assert response.status_code == 200, response.text
            assert len(start.await_args.kwargs["items"]) == 1
            start.reset_mock()
            response = await async_client.post("/api/jobs/start", json={"job_type": "check_backup_recreated", "params": {"backup_ids": [backup_id, "unavailable"]}})
            assert response.status_code == 404
            start.assert_not_awaited()
            reader.read_sendtask.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("created", [None, 0, -1, "bad"])
async def test_invalid_remote_version_is_error_not_unproven_present(schema_engine, created):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old")).returning(TaskBackup.backup_id))
    value = snapshot().task
    value["sendtask_create_ut"] = created
    reader = AsyncMock(read_sendtask=AsyncMock(return_value={"data": value}))
    result = await BackupCheckService(factory, reader).check([backup_id], scope=["org-1"])
    assert result["job_status"] == "failed" and result["failed_count"] == 1
    async with factory() as session:
        backup = await session.get(TaskBackup, backup_id)
        assert backup.latest_remote_status == "error" and backup.recreated_detected_at is None
        assert backup.last_remote_create_ut is None and backup.last_remote_checked_at is not None


@pytest.mark.asyncio
async def test_invalid_source_version_is_error_even_when_remote_is_present(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old", source_create_ut=None)).returning(TaskBackup.backup_id))
    reader = AsyncMock(read_sendtask=AsyncMock(return_value={"data": snapshot().task}))
    result = await BackupCheckService(factory, reader).check([backup_id], scope=None)
    assert result["failed_count"] == 1
    assert result["backup_observations"][0]["latest_remote_status"] == "error"
    assert result["backup_observations"][0]["recreated_detected_at"] is None


@pytest.mark.asyncio
async def test_pretest_uses_snapshot_mode_and_failure_does_not_become_missing(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("pre", task_snapshot={"pre_test_enable": True})).returning(TaskBackup.backup_id))
    reader = AsyncMock(read_sendtask=AsyncMock(side_effect=TaskReadError("pretest_not_found")))
    result = await BackupCheckService(factory, reader).check([backup_id], scope=["org-1"])
    reader.read_sendtask.assert_awaited_once_with("task-1", sendlog_type="pretest")
    assert result["backup_observations"][0]["latest_remote_status"] == "error"


@pytest.mark.asyncio
async def test_check_keeps_all_fixed_payloads_and_current_data_unchanged(schema_engine):
    import hashlib
    import json
    from backend.repository.models import TaskBackupDetail, SendTask, SendLogDetail, SendLogStats

    factory, engine, _ = await setup_transfer(schema_engine)
    async with task_sync_transaction(factory, await read_expected_task_version(factory, "task-1")) as locked:
        transferred = await transfer_task_to_backup(locked, reason="manual_reload")
    async with engine.begin() as conn:
        await conn.execute(insert(SendTask).values(sendtask_uuid="task-1", sendtask_id="New", sendtask_owner_gid=["org-2"]))

    async def digest():
        async with factory() as session:
            backup = await session.get(TaskBackup, transferred.backup_id)
            fixed = {field: getattr(backup, field) for field in (
                "task_snapshot", "stats_snapshot", "mail_template_snapshot", "stats_snapshot_at", "reason", "source_create_ut",
            )}
            fixed["details"] = [dict(row) for row in (await session.execute(select(TaskBackupDetail.__table__).order_by(TaskBackupDetail.id))).mappings()]
            fixed["current"] = [dict(row) for row in (await session.execute(select(SendTask.__table__))).mappings()]
            return hashlib.sha256(json.dumps(fixed, sort_keys=True, default=str).encode()).hexdigest()

    before = await digest()
    reader = AsyncMock(read_sendtask=AsyncMock(return_value={"data": snapshot(200).task}))
    await BackupCheckService(factory, reader).check([transferred.backup_id], scope=["org-1"])
    assert await digest() == before
    assert await current_counts(factory) == (1, 0, 0, 1, 2)


@pytest.mark.asyncio
async def test_older_manual_query_cannot_override_newer_core_observation(schema_engine):
    from backend.services.task_sync_core import TaskSyncService

    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old")).returning(TaskBackup.backup_id))

    async def remote(task_uuid, **kwargs):
        async with factory() as session:
            async with session.begin():
                await TaskSyncService._observe_backups(session, task_uuid, 300, ["org-1"])
        return {"data": snapshot(100).task}

    reader = AsyncMock(read_sendtask=AsyncMock(side_effect=remote))
    result = await BackupCheckService(factory, reader).check([backup_id], scope=["org-1"])
    assert not result["backup_observations"][0]["applied"]
    async with factory() as session:
        backup = await session.get(TaskBackup, backup_id)
        assert backup.last_remote_create_ut == 300 and backup.recreated_detected_at is not None


@pytest.mark.asyncio
async def test_second_source_transaction_failure_preserves_first_commit(schema_engine):
    from backend.tests.repository.test_task_backup_schema import set_path

    factory, engine, schema = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        ids = [await conn.scalar(insert(TaskBackup).values(**backup_values(str(number), source_task_uuid=f"task-{number}")).returning(TaskBackup.backup_id)) for number in (1, 2)]
        await set_path(conn, schema)
        await conn.execute(text("CREATE FUNCTION fail_observation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.source_task_uuid='task-2' THEN RAISE EXCEPTION 'injected observation'; END IF; RETURN NEW; END $$"))
        await conn.execute(text("CREATE TRIGGER fail_observation BEFORE UPDATE ON task_backups FOR EACH ROW EXECUTE FUNCTION fail_observation()"))

    async def remote(task_uuid, **kwargs):
        value = snapshot(200).task
        value["sendtask_uuid"] = task_uuid
        return {"data": value}

    result = await BackupCheckService(factory, AsyncMock(read_sendtask=AsyncMock(side_effect=remote))).check(ids, scope=None)
    assert result["job_status"] == "partial" and result["checked_count"] == 1 and result["failed_count"] == 1
    assert result["backup_check_items"]["task-2"] == "backup_check_error"
    async with factory() as session:
        assert (await session.get(TaskBackup, ids[0])).latest_remote_status == "present"
        assert (await session.get(TaskBackup, ids[1])).latest_remote_status == "unchecked"


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{}, {"backup_ids": []}, {"backup_ids": "one"}, {"backup_ids": [None]},
    {"backup_ids": ["one"], "source_uuid": "task-1"}, {"backup_ids": ["one"], "orgs": ["org-1"]}])
async def test_job_requires_only_explicit_backup_ids(async_client, params):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "username": "user-a", "orgs": ["org-1"]}
    try:
        with patch.object(job_api.job_manager, "start_job", AsyncMock()) as start:
            response = await async_client.post("/api/jobs/start", json={"job_type": "check_backup_recreated", "params": params})
        assert response.status_code == 400
        start.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity,expected", [(None, 401), ({"user_type": "customer", "admin_role": True}, 403),
    ({"user_type": "user", "orgs": []}, 403)])
async def test_job_identity_rejected_before_read(async_client, identity, expected):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    if identity is not None:
        app.dependency_overrides[get_current_user] = lambda: identity
    try:
        with patch.object(job_api.db_user, "get_task_sync") as core:
            response = await async_client.post("/api/jobs/start", json={"job_type": "check_backup_recreated", "params": {"backup_ids": ["one"]}})
        assert response.status_code == expected
        core.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_observation_filters_distinguish_evidence_from_latest_error(async_client, schema_engine):
    from backend.api import task_backup_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        ids = {}
        for generation, status, detected in (("rebuilt", "error", datetime.now(timezone.utc)),
            ("same", "present", None), ("unseen", "unchecked", None), ("failed", "error", None)):
            ids[generation] = await conn.scalar(insert(TaskBackup).values(**backup_values(generation,
                latest_remote_status=status, recreated_detected_at=detected)).returning(TaskBackup.backup_id))
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "orgs": ["org-1"]}
    try:
        with patch.object(task_backup_api, "async_session", factory):
            for value, names in (("recreated", ["rebuilt"]), ("unproven", ["same", "unseen", "failed"]),
                                 ("unchecked", ["unseen"]), ("error", ["rebuilt", "failed"])):
                response = await async_client.get("/api/task_backups", params={"observation": value})
                assert response.status_code == 200
                assert {row["backup_id"] for row in response.json()["data"]} == {ids[name] for name in names}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_real_queue_keeps_observation_and_item_after_cancel(schema_engine):
    from backend.repository.models import JobRun, JobRunItem
    from backend.services.job_queue import JobQueue

    factory, engine, _ = await setup_transfer(schema_engine)
    queue = JobQueue()
    async with engine.begin() as conn:
        ids = [await conn.scalar(insert(TaskBackup).values(**backup_values(str(number), source_task_uuid=f"task-{number}")).returning(TaskBackup.backup_id)) for number in (1, 2)]
        await conn.execute(insert(JobRun).values(job_id="check-job", source="manual", owner_username="user-a",
            job_type="check", status="running", claimed_by=queue.worker_id))
        for number in (1, 2):
            await conn.execute(insert(JobRunItem).values(job_id="check-job", sendtask_uuid=f"task-{number}",
                sendtask_id="Task", status="running"))
    reader = AsyncMock(read_sendtask=AsyncMock(side_effect=[{"data": snapshot(200).task}, asyncio.CancelledError]))
    queue.register("check", lambda job_id: BackupCheckService(factory, reader).check(ids, scope=["org-1"]))
    with patch("backend.services.job_queue.async_session", factory):
        await queue._run_claimed("check-job", "check")
    async with factory() as session:
        job = await session.scalar(select(JobRun))
        assert job.status == "cancelled"
        assert job.result["backups_changed"] and job.result["changed_backup_ids"] == [ids[0]]
        assert job.result["changed_uuids"] == [] and not job.result["reload_list"]
        items = (await session.scalars(select(JobRunItem).order_by(JobRunItem.sendtask_uuid))).all()
        assert [(item.status, item.reason) for item in items] == [("completed", "backup_check_present"), ("cancelled", "cancelled")]


@pytest.mark.asyncio
async def test_execution_revalidates_all_selected_backups_before_remote_read(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("one")).returning(TaskBackup.backup_id))
    reader = AsyncMock()
    from backend.services.backup_check import select_backup_targets

    await select_backup_targets(factory, [backup_id], ["org-1"])
    async with engine.begin() as conn:
        await conn.execute(update(TaskBackup).values(owner_gids=["org-2"]))
    with pytest.raises(HTTPException):
        await BackupCheckService(factory, reader).check([backup_id], scope=["org-1"])
    reader.read_sendtask.assert_not_awaited()


@pytest.mark.asyncio
async def test_later_backup_deleted_mid_check_returns_partial_without_querying_it(schema_engine):
    from sqlalchemy import delete

    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        ids = [await conn.scalar(insert(TaskBackup).values(**backup_values(str(number), source_task_uuid=f"task-{number}")).returning(TaskBackup.backup_id)) for number in (1, 2)]

    async def remote(task_uuid, **kwargs):
        async with engine.begin() as conn:
            await conn.execute(delete(TaskBackup).where(TaskBackup.backup_id == ids[1]))
        return {"data": snapshot(200).task}

    reader = AsyncMock(read_sendtask=AsyncMock(side_effect=remote))
    result = await BackupCheckService(factory, reader).check(ids, scope=["org-1"])
    assert result["job_status"] == "partial" and result["checked_count"] == 1
    reader.read_sendtask.assert_awaited_once()


@pytest.mark.asyncio
async def test_core_missing_updates_authorized_observation_without_clearing_evidence(schema_engine):
    from backend.services.task_sync_core import TaskSyncService

    factory, engine, _ = await setup_transfer(schema_engine)
    evidence = datetime.now(timezone.utc) - timedelta(days=1)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old", recreated_detected_at=evidence)).returning(TaskBackup.backup_id))
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(side_effect=TaskNotFound("missing"))))
    with patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(return_value=AsyncMock())):
        result = await core.sync("task-1", orgs=["org-1"])
    assert result.status == "backed_up"
    async with factory() as session:
        backup = await session.get(TaskBackup, backup_id)
        assert backup.latest_remote_status == "missing" and backup.recreated_detected_at == evidence