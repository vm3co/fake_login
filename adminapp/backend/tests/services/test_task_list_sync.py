import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest
from sqlalchemy import insert, select, update

from backend.repository.models import SendTask, TaskBackup
from backend.services.task_list_sync import TaskListSyncService
from backend.services.task_sync_core import TaskSyncService, TaskSyncAccessDenied
from backend.services.se2_task_reader import TaskNotFound, TaskReadError
from backend.services.db_user import DBUser
from backend.tests.repository.test_task_backup_schema import schema_engine, backup_values
from backend.tests.services.test_task_backup_transfer import setup_transfer, current_counts
from backend.tests.services.test_task_sync_core import snapshot
from backend.tests.services.test_task_archive_policy import NOW, CUTOFF


def reader_for(value, listing=None):
    return AsyncMock(
        read_sendtasks=AsyncMock(return_value=[] if listing is None else listing),
        read_task_snapshot=AsyncMock(return_value=value),
        read_sendtask=AsyncMock(return_value={"data": value.task, "metadata": value.metadata}),
    )


@pytest.mark.asyncio
async def test_archived_missing_from_list_still_recreates_and_refreshes(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(is_archived=True))
    value = snapshot(200, 5)
    value.task["test_end_ut"] = NOW + 1
    reader = reader_for(value)
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "success"
    assert len(result["recreated"]) == len(result["unarchived_tasks"]) == 1
    assert await current_counts(factory) == (1, 5, 1, 1, 2)
    reader.read_task_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_remote_list_failure_does_not_touch_any_task(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    reader.read_sendtasks.side_effect = TaskReadError("incomplete_pages")
    with pytest.raises(TaskReadError):
        await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    reader.read_task_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_excludes_other_local_and_remote_tasks(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(orgs=["org-2"])
    reader = reader_for(value, [value.task])
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-2"])
    assert result["results"] == []
    reader.read_sendtask.assert_not_awaited()
    reader.read_task_snapshot.assert_not_awaited()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [[], (), "org-1"])
async def test_empty_or_invalid_scope_never_reads_remote(schema_engine, scope):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    with pytest.raises(TaskSyncAccessDenied):
        await TaskListSyncService(TaskSyncService(factory, reader)).sync(orgs=scope)
    reader.read_sendtasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_backups_outside_window_are_deduplicated_and_imported(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        for generation in ("history-1", "history-2"):
            await conn.execute(insert(TaskBackup).values(**backup_values(
                generation, source_task_uuid="history-task", source_create_ut=50,
            )))
    value = snapshot(200, 0)
    value.task["sendtask_uuid"] = value.testcase["testcase_uuid"] = "history-task"
    value.task["test_end_ut"] = CUTOFF - 1
    reader = reader_for(value)
    reader.read_task_snapshot.side_effect = lambda task_uuid, **kwargs: snapshot() if task_uuid == "task-1" else value

    async def detail(task_uuid, **kwargs):
        current = snapshot() if task_uuid == "task-1" else value
        return {"data": current.task, "metadata": current.metadata}

    reader.read_sendtask.side_effect = detail
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "success", result["failed_tasks"]
    assert len(result["added"]) == 1
    assert reader.read_task_snapshot.await_count == 2
    async with factory() as session:
        backups = (await session.scalars(select(TaskBackup))).all()
        assert all(backup.recreated_detected_at is not None for backup in backups)
        assert await session.scalar(select(SendTask.is_archived).where(SendTask.sendtask_uuid == "history-task")) is True


@pytest.mark.asyncio
async def test_missing_backups_only_are_unchanged_without_new_snapshot(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(**backup_values("history", source_task_uuid="history-task")))
    reader = reader_for(snapshot())

    async def read_detail(task_uuid, **kwargs):
        if task_uuid == "history-task":
            raise TaskNotFound("missing")
        return {"data": snapshot().task, "metadata": snapshot().metadata}

    async def read_snapshot(task_uuid, **kwargs):
        if task_uuid == "history-task":
            raise TaskNotFound("missing")
        return snapshot()

    reader.read_sendtask.side_effect = read_detail
    reader.read_task_snapshot.side_effect = read_snapshot
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "success"
    assert [item.status for item in result["results"]] == ["unchanged", "updated"]
    assert await current_counts(factory) == (1, 2, 1, 1, 0)


@pytest.mark.asyncio
async def test_one_failed_task_reports_partial_and_keeps_committed_success(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    broken = {**snapshot().task, "sendtask_uuid": "broken"}
    reader = reader_for(snapshot(), [broken])

    async def detail(task_uuid, **kwargs):
        if task_uuid == "broken":
            raise TaskReadError("transport_error")
        return {"data": snapshot().task, "metadata": snapshot().metadata}

    reader.read_sendtask.side_effect = detail
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "partial" and len(result["failed_tasks"]) == 1
    assert result["changed_uuids"] == ["task-1"]
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("end,imported", [(CUTOFF - 1, False), (CUTOFF, True), (NOW - 7 * 86400, True), (None, True)])
async def test_new_discovery_uses_fourteen_day_policy(schema_engine, end, imported):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(200, 0)
    value.task["sendtask_uuid"] = value.testcase["testcase_uuid"] = "new-task"
    value.task["test_end_ut"] = end
    reader = reader_for(value, [value.task])
    reader.read_task_snapshot.side_effect = lambda task_uuid, **kwargs: snapshot() if task_uuid == "task-1" else value

    async def detail(task_uuid, **kwargs):
        current = snapshot() if task_uuid == "task-1" else value
        return {"data": current.task, "metadata": current.metadata}

    reader.read_sendtask.side_effect = detail
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert bool(result["added"]) is imported
    assert bool(result["skipped"]) is not imported


@pytest.mark.asyncio
async def test_remote_scope_change_blocks_detail_snapshot(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot(orgs=["org-2"]))
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "partial"
    reader.read_task_snapshot.assert_not_awaited()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_cancellation_propagates_after_reporting_committed_result(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    results = []

    async def on_result(result):
        results.append(result)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=None, on_result=on_result)
    assert len(results) == 1 and results[0].committed
    async with factory() as session:
        assert await session.scalar(select(SendTask.sync_revision)) == 1


@pytest.mark.asyncio
async def test_confirmed_missing_moves_once_but_failed_read_preserves_current(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    reader.read_sendtask.side_effect = TaskReadError("http_error")
    service = TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW)
    result = await service.sync(orgs=["org-1"])
    assert result["status"] == "partial"
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    reader.read_sendtask.side_effect = TaskNotFound("missing")
    reader.read_task_snapshot.side_effect = TaskNotFound("missing")
    for count in (1, 0):
        result = await service.sync(orgs=["org-1"])
        assert result["status"] == "success" and len(result["backed_up"]) == count
        assert result["deleted"] == 0
        assert await current_counts(factory) == (0, 0, 0, 1, 2)


@pytest.mark.asyncio
async def test_org_a_never_reads_org_b_backup_source(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(**backup_values(
            "other-history", source_task_uuid="org-b-task", owner_gids=["org-2"],
        )))
    reader = reader_for(snapshot())
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "success"
    reader.read_sendtask.assert_awaited_once_with("task-1", sendlog_type="test")
    async with factory() as session:
        backup = await session.scalar(select(TaskBackup))
        assert backup.latest_remote_status == "unchecked"


@pytest.mark.asyncio
async def test_same_version_extension_unarchives_and_refreshes_statistics(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(is_archived=True, test_end_ut=CUTOFF - 1))
    value = snapshot(100, 3)
    value.task["test_end_ut"] = NOW + 86400
    reader = reader_for(value)
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=None)
    assert result["status"] == "success" and len(result["unarchived_tasks"]) == 1
    assert await current_counts(factory) == (1, 3, 1, 0, 0)


@pytest.mark.asyncio
async def test_backup_pretest_mode_is_preserved(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(**backup_values(
            "pretest", source_task_uuid="pretest-task", task_snapshot={"pre_test_enable": True},
        )))
    reader = reader_for(snapshot())

    async def detail(task_uuid, **kwargs):
        if task_uuid == "pretest-task":
            raise TaskReadError("pretest_not_found_is_not_deletion")
        return {"data": snapshot().task, "metadata": snapshot().metadata}

    reader.read_sendtask.side_effect = detail
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "partial"
    assert reader.read_sendtask.await_args_list[0].kwargs["sendlog_type"] == "pretest"


@pytest.mark.asyncio
async def test_db_user_delegates_only_when_explicitly_injected():
    service = AsyncMock()
    service.sync.return_value = {"versioned": True}
    assert DBUser().task_list_sync is None
    assert await DBUser(task_list_sync=service).sync_sendtasks(orgs=["org-1"]) == {"versioned": True}
    service.sync.assert_awaited_once_with(orgs=["org-1"], on_result=ANY)


@pytest.mark.asyncio
async def test_worker_uses_same_policy_without_enabling_scheduler():
    from backend.workers.archiving_worker import ArchivingWorker

    rows = [SimpleNamespace(
        sendtask_uuid=task_uuid, test_end_ut=end, pre_test_end_ut=None, stop_time_new=-1,
    ) for task_uuid, end in (("old", CUTOFF - 1), ("boundary", CUTOFF), ("unknown", None), ("bad", -2))]
    redis = AsyncMock()
    execute = AsyncMock(side_effect=[SimpleNamespace(all=lambda: rows), None])
    with patch("backend.workers.archiving_worker.time.time", return_value=NOW), \
         patch("backend.workers.archiving_worker.db_controller.execute", new=execute), \
         patch("backend.workers.archiving_worker.RedisClient.get_client", new=AsyncMock(return_value=redis)):
        await ArchivingWorker().archive_old_tasks()
    assert execute.await_count == 2
    redis.delete.assert_awaited_once_with("task:old:details")


@pytest.mark.asyncio
async def test_list_job_preserves_versioned_outcomes_without_legacy_refresh(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    service = AsyncMock()
    task = {"sendtask_uuid": "task-1", "sendtask_id": "Remote"}
    service.sync.return_value = {
        "versioned": True, "status": "partial", "added": [task], "changed": [],
        "recreated": [task], "backed_up": [task], "unarchived_tasks": [task],
        "failed_tasks": [{**task, "reason": "read_error"}], "changed_uuids": ["task-1"],
        "backups_changed": True, "archived": 0, "deleted": 0,
    }
    captured = {}

    async def start_job(username, name, task_func, **kwargs):
        captured.update(await task_func())
        return {"job_id": "list-job", "accepted": [], "excluded": []}

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user", "username": "user-a", "orgs": ["org-1"], "admin_role": False,
    }
    refresh = AsyncMock()
    try:
        with patch("backend.api.job_api.db_user", new=DBUser(task_list_sync=service)), \
             patch("backend.api.job_api.DBUser.refresh_sendlog_stats", new=refresh), \
             patch("backend.api.job_api.job_manager.start_job", new=start_job):
            response = await async_client.post("/api/jobs/start", json={"job_type": "check_sendtasks", "params": {}})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    assert captured["status"] == "partial"
    assert captured["recreated_count"] == captured["backed_up_count"] == captured["unarchived_count"] == captured["failed_count"] == 1
    service.sync.assert_awaited_once_with(orgs=["org-1"], on_result=ANY)
    refresh.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("listing", [None, {}, [snapshot().task, snapshot().task], [{"sendtask_uuid": "broken"}]])
async def test_incomplete_or_malformed_list_never_starts_task_writes(schema_engine, listing):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    reader.read_sendtasks.return_value = listing
    with pytest.raises(TaskReadError):
        await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=None)
    reader.read_sendtask.assert_not_awaited()
    reader.read_task_snapshot.assert_not_awaited()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_notification_failure_does_not_hide_commit_or_stop_next_task(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    notify = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=None, on_result=notify)
    assert result["status"] == "success" and not result["failed_tasks"]
    assert len(result["notification_errors"]) == 1
    assert result["results"][0].committed and result["changed_uuids"] == ["task-1"]


@pytest.mark.asyncio
async def test_cancellation_during_remote_read_preserves_current(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    reader = reader_for(snapshot())
    reader.read_task_snapshot.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_invalid_end_time_is_partial_and_preserves_task(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot()
    value.task["test_end_ut"] = "bad"
    reader = reader_for(value)
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "partial" and not result["changed_uuids"]
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_list_already_outside_scope_does_not_fetch_single_task(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(orgs=["org-2"])
    reader = reader_for(value, [value.task])
    result = await TaskListSyncService(TaskSyncService(factory, reader), clock=lambda: NOW).sync(orgs=["org-1"])
    assert result["status"] == "success" and not result["results"]
    reader.read_sendtask.assert_not_awaited()
    reader.read_task_snapshot.assert_not_awaited()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)