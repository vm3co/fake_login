import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from backend.services.db_user import DBUser
from backend.services.task_sync_core import TaskSyncResult, TaskSyncAccessDenied
from backend.services.task_sync_entrypoints import TaskSyncCancelled
from backend.services.se2_task_reader import TaskNotFound
from backend.tests.repository.test_task_backup_schema import schema_engine
from backend.tests.services.test_task_backup_transfer import setup_transfer, current_counts
from backend.tests.services.test_task_sync_core import snapshot


def outcome(task_uuid, status="recreated"):
    return TaskSyncResult(status, task_uuid, "new-generation", 0, "backup-1", True, (task_uuid,), True)


@pytest.mark.asyncio
async def test_manual_scheduler_warming_race_preserves_single_backup(schema_engine):
    from backend import main
    from backend.api import job_api
    from backend.services.task_sync_core import TaskSyncService

    factory, _, _ = await setup_transfer(schema_engine)
    ready = asyncio.Event()
    arrivals = 0

    async def read_snapshot(*args, **kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 3:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=10)
        return snapshot(200, 5)

    reader = AsyncMock(read_task_snapshot=AsyncMock(side_effect=read_snapshot))
    user = DBUser(task_sync=TaskSyncService(factory, reader))
    tasks = [SimpleNamespace(sendtask_uuid='task-1')]
    with patch.object(main, 'db_user', user), patch.object(job_api, 'db_user', user), \
         patch.object(main.db_controller, 'get', AsyncMock(return_value=tasks)), \
         patch.object(job_api.job_manager, 'mark_item', AsyncMock()):
        results = await asyncio.wait_for(asyncio.gather(
            main.refresh_sendlog_stats_job(), main.run_cache_warming(),
            job_api.sync_job_items([{'sendtask_uuid': 'task-1', 'sendtask_id': 'Original'}], 'race', orgs=['org-1']),
        ), timeout=20)
    assert arrivals == 3
    assert await current_counts(factory) == (1, 5, 1, 1, 2)
    assert sum(result['recreated_count'] for result in results) == 1
    assert sum(result['failed_count'] for result in results) == 2


@pytest.mark.asyncio
async def test_batch_only_delegates_to_core_and_deduplicates():
    core = AsyncMock(session_factory=None)
    core.sync.return_value = outcome("task-1")
    forbidden = AsyncMock(side_effect=AssertionError("Legacy write must not run"))
    with patch("backend.services.db_user.db_controller.upsert", new=forbidden), \
         patch("backend.services.db_user.db_controller.delete", new=forbidden):
        result = await DBUser(task_sync=core).sync_tasks(["task-1", "task-1"], orgs=["org-1"])
    assert result == {"task-1": "recreated"}
    assert result.results["task-1"].committed
    core.sync.assert_awaited_once_with("task-1", orgs=["org-1"], archive_at=ANY)


@pytest.mark.asyncio
async def test_failure_preserves_committed_results():
    core = AsyncMock(session_factory=None)
    core.sync.side_effect = [outcome("first"), RuntimeError("read failed")]
    result = await DBUser(task_sync=core).sync_tasks(["first", "second"], orgs=None)
    assert result == {"first": "recreated", "second": "error"}
    assert result.errors == {"second": "read failed"}
    assert result.results["first"].committed


@pytest.mark.asyncio
async def test_cancellation_exposes_prior_commits():
    core = AsyncMock(session_factory=None)
    core.sync.side_effect = [outcome("first"), asyncio.CancelledError]
    with pytest.raises(TaskSyncCancelled) as error:
        await DBUser(task_sync=core).sync_tasks(["first", "second"], orgs=None)
    assert error.value.results.results["first"].committed


@pytest.mark.asyncio
async def test_empty_scope_is_rejected_before_core():
    core = AsyncMock(session_factory=None)
    with pytest.raises(TaskSyncAccessDenied):
        await DBUser(task_sync=core).sync_tasks(["task-1"], orgs=[])
    core.sync.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["refresh_sendlog_stats", "check_sendlog", "sendlog_write", "upsert_sendtasks_by_uuids"])
async def test_legacy_entrypoints_never_write_before_core(method):
    core = AsyncMock(session_factory=None)
    core.sync.return_value = outcome("task-1", "backed_up")
    user = DBUser(task_sync=core)
    forbidden = AsyncMock(side_effect=AssertionError("Legacy write must not run"))
    with patch("backend.services.db_user.db_controller.upsert", new=forbidden), \
         patch("backend.services.db_user.db_controller.delete", new=forbidden):
        arguments = {"task-1": 100} if method == "check_sendlog" else ["task-1"]
        await getattr(user, method)(arguments, orgs=["org-1"])
    core.sync.assert_awaited_once_with("task-1", orgs=["org-1"], archive_at=ANY)


@pytest.mark.asyncio
async def test_skip_flag_cannot_skip_version_check():
    core = AsyncMock(session_factory=None)
    core.sync.return_value = outcome("task-1")
    statuses = await DBUser(task_sync=core).refresh_sendlog_stats(["task-1"], skip_sendtask_sync=True)
    assert statuses["task-1"] == "recreated"
    core.sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_discovery_is_strict_and_read_only():
    core = AsyncMock(session_factory=None)
    core.reader.read_sendtasks.return_value = [{"sendtask_uuid": "task-1"}]
    user = DBUser(task_sync=core)
    assert await user.refresh_today_create_task() == [{"sendtask_uuid": "task-1"}]
    assert "start_time" in core.reader.read_sendtasks.await_args.kwargs
    await user.search_sendtasks_by_keyword("name")
    core.reader.read_sendtasks.assert_awaited_with(keyword="name")
    core.sync.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type", ["refresh_sendlog_stats", "upsert_selected_sendtasks"])
async def test_manual_jobs_authorize_then_sync_once(async_client, job_type):
    from backend.api import job_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    core = AsyncMock(session_factory=None)
    core.sync.return_value = outcome("allowed")
    user = DBUser(task_sync=core)
    captured = {}

    async def start_job(username, name, task_func, **kwargs):
        captured.update(await task_func(accepted_items=kwargs["items"], job_id="job-1"))
        return {"job_id": "job-1", "accepted": kwargs["items"], "excluded": []}

    rows = [SimpleNamespace(sendtask_uuid=task_uuid, sendtask_id=task_uuid, sendtask_owner_gid=orgs)
            for task_uuid, orgs in (("allowed", ["org-1"]), ("denied", ["org-2"]))]
    get_one = AsyncMock(side_effect=lambda model, filters: next(row for row in rows if row.sendtask_uuid == filters["sendtask_uuid"]))
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "user-a", "user_type": "user", "admin_role": False, "orgs": ["org-1"],
    }
    try:
        with patch.object(job_api, "db_user", user), \
             patch.object(job_api.db_controller, "get", AsyncMock(return_value=rows)), \
             patch.object(job_api.db_controller, "get_one", get_one), \
             patch.object(job_api.db_controller, "upsert", AsyncMock(side_effect=AssertionError("No header upsert"))), \
             patch.object(job_api.job_manager, "start_job", start_job), \
             patch.object(job_api.job_manager, "mark_item", AsyncMock()):
            response = await async_client.post("/api/jobs/start", json={
                "job_type": job_type, "params": {"uuids": ["allowed", "denied"], "orgs": ["org-2"]},
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200, response.text
    core.sync.assert_awaited_once_with("allowed", orgs=["org-1"], archive_at=ANY)
    assert captured["recreated_count"] == 1 and captured["job_status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_start_preserves_customer_tracking_and_reports_sync_separately(failed):
    from backend.api import create_task_api as api

    core = AsyncMock(session_factory=None)
    core.sync.return_value = outcome("real-task")
    if failed:
        core.sync.side_effect = RuntimeError("remote read failed")
    user = DBUser(task_sync=core)
    tracking = AsyncMock()
    update = AsyncMock()
    with patch.object(api.se_task_service, "create_sendtask", AsyncMock(return_value={"data": {"sendtask_uuid": "real-task"}})), \
         patch.object(api, "DBUser", return_value=user), \
         patch.object(api.db_controller, "update", update), \
         patch.object(api.db_controller, "get_one", AsyncMock(return_value=SimpleNamespace(customer_uuid="customer-1"))), \
         patch.object(api.db_controller, "upsert", AsyncMock(side_effect=AssertionError("No header upsert"))), \
         patch.object(api, "_add_sendtask_to_customer", tracking):
        response = await api.create_sendtask(api.SendtaskUuidRequest(sendtask_uuid="testcase"))
    assert response["status"] == "success" and response["sendtask_uuid"] == "real-task"
    assert response["sync_status"] == ("error" if failed else "recreated")
    assert bool(response["local_errors"]) is failed
    tracking.assert_awaited_once_with("customer-1", "real-task")
    core.sync.assert_awaited_once_with("real-task", orgs=None, archive_at=ANY)


@pytest.mark.asyncio
async def test_scheduler_and_warming_keep_scopes_without_upserting_headers():
    from backend import main

    core = AsyncMock(session_factory=None)
    core.reader.read_sendtasks.return_value = [{"sendtask_uuid": "task-1", "sendtask_id": "Remote"}]
    core.sync.return_value = outcome("task-1")
    user = DBUser(task_sync=core)
    with patch.object(main, "db_user", user), \
         patch.object(main.db_controller, "get", AsyncMock(return_value=[SimpleNamespace(sendtask_uuid="task-1")])), \
         patch.object(main.db_controller, "upsert", AsyncMock(side_effect=AssertionError("No header upsert"))):
        today = await main.refresh_today_create_task_job()
        assert today["recreated_count"] == 1
        await main.run_cache_warming()
        await main.refresh_sendlog_stats_job()
    assert core.sync.await_count == 3
    assert all(call.kwargs["orgs"] is None for call in core.sync.await_args_list)


@pytest.mark.asyncio
async def test_nightly_uses_list_policy_without_second_refresh():
    from backend import main

    service = AsyncMock()
    service.sync.return_value = {"status": "success", "added": [], "changed": [], "deleted": 0, "archived": 0, "results": []}
    user = DBUser(task_list_sync=service)
    with patch.object(main, "db_user", user), \
         patch.object(user, "refresh_sendlog_stats", AsyncMock(side_effect=AssertionError("No duplicate refresh"))):
        result = await main.nightly_sync_job()
    assert "results" not in result
    service.sync.assert_awaited_once_with(orgs=None, on_result=ANY)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["refresh", "check", "sendlog", "upsert", "today", "warming", "nightly", "start", "manual", "notyet"])
@pytest.mark.parametrize("missing", [False, True])
async def test_real_postgres_entrypoints_replace_or_backup_atomically(schema_engine, entry, missing):
    from backend import main
    from backend.api import job_api, create_task_api
    from backend.services.task_sync_core import TaskSyncService

    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(200, 5)
    reader = AsyncMock()
    reader.read_sendtasks.return_value = [value.task]
    reader.read_sendtask.return_value = {"data": value.task, "metadata": value.metadata}
    reader.read_task_snapshot.return_value = value
    if missing:
        reader.read_sendtask.side_effect = TaskNotFound("confirmed_missing")
        reader.read_task_snapshot.side_effect = TaskNotFound("confirmed_missing")
    user = DBUser(task_sync=TaskSyncService(factory, reader))
    tasks = [{"sendtask_uuid": "task-1", "sendtask_id": "Original"}]
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [
        SimpleNamespace(sendtask_uuid="task-1", todayunsend=1, todayfailed=0),
    ]))
    context = AsyncMock()
    context.__aenter__.return_value = session
    forbidden = AsyncMock(side_effect=AssertionError("No legacy task write"))
    with patch.object(main, "db_user", user), patch.object(job_api, "db_user", user), \
         patch.object(create_task_api, "DBUser", return_value=user), \
         patch.object(main.db_controller, "get", AsyncMock(return_value=[SimpleNamespace(sendtask_uuid="task-1")])), \
         patch.object(main.db_controller, "get_session", return_value=context), \
         patch.object(main.db_controller, "upsert", forbidden), \
         patch.object(main.db_controller, "delete", forbidden), \
         patch.object(job_api.job_manager, "mark_item", AsyncMock()), \
         patch.object(create_task_api.se_task_service, "create_sendtask", AsyncMock(return_value={"sendtask_uuid": "task-1"})), \
         patch.object(create_task_api.db_controller, "update", AsyncMock()), \
         patch.object(create_task_api.db_controller, "get_one", AsyncMock(return_value=None)):
        if entry == "refresh":
            await user.refresh_sendlog_stats(["task-1"], orgs=["org-1"])
        elif entry == "check":
            await user.check_sendlog({"task-1": 100}, orgs=["org-1"])
        elif entry == "sendlog":
            await user.sendlog_write(["task-1"], orgs=["org-1"])
        elif entry == "upsert":
            await user.upsert_sendtasks_by_uuids(["task-1"], orgs=["org-1"])
        elif entry == "today":
            await main.refresh_today_create_task_job()
        elif entry == "warming":
            await main.run_cache_warming()
        elif entry == "nightly":
            await main.nightly_sync_job()
        elif entry == "start":
            result = await create_task_api.create_sendtask(create_task_api.SendtaskUuidRequest(sendtask_uuid="task-1"))
            assert result["status"] == "success"
        elif entry == "manual":
            result = await job_api.sync_job_items(tasks, "job-1", orgs=["org-1"])
            assert result["backed_up_count" if missing else "recreated_count"] == 1
        else:
            await main.refresh_notyet_today_tasks_job()
    assert await current_counts(factory) == ((0, 0, 0, 1, 2) if missing else (1, 5, 1, 1, 2))
    reader.read_task_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_table_initialization_uses_list_service_not_batch_create():
    from backend.repository.models import SendTask, Acct, Mtmpl, SendLogStats

    user = DBUser(task_list_sync=AsyncMock())
    user.task_list_sync.sync.return_value = {"status": "success"}

    async def get(model, *args, **kwargs):
        return [] if model is SendTask else [SimpleNamespace()]

    with patch("backend.services.db_user.db_controller.get", AsyncMock(side_effect=get)), \
         patch("backend.services.db_user.db_controller.batch_create", AsyncMock(side_effect=AssertionError("No task batch create"))):
        await user.table_initialize()
    user.task_list_sync.sync.assert_awaited_once_with(orgs=None, on_result=ANY)


@pytest.mark.asyncio
async def test_notyet_scheduler_keeps_original_selection():
    from backend import main

    core = AsyncMock(session_factory=None)
    core.sync.side_effect = lambda task_uuid, **kwargs: outcome(task_uuid)
    rows = [SimpleNamespace(sendtask_uuid=task_uuid, todayunsend=unsent, todayfailed=failed)
            for task_uuid, unsent, failed in (("unsent", 1, 0), ("failed", 0, 1), ("done", 0, 0))]
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    context = AsyncMock()
    context.__aenter__.return_value = session
    with patch.object(main, "db_user", DBUser(task_sync=core)), \
         patch.object(main.db_controller, "get_session", return_value=context):
        result = await main.refresh_notyet_today_tasks_job()
    assert result["successful_count"] == 2
    assert [call.args[0] for call in core.sync.await_args_list] == ["unsent", "failed"]
    assert "today_earliest_plan_time" in str(session.execute.await_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["check_sendtasks", "refresh_today_create_task", "upsert_selected_sendtasks", "refresh_sendlog_stats"])
async def test_disabled_data_endpoints_remain_gone(async_client, endpoint):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {"username": "admin", "admin_role": True}
    try:
        response = await async_client.post("/api/" + endpoint, json={"orgs": [], "sendtask_uuids": []})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 410


def test_scheduler_switches_and_schedule_are_preserved():
    from backend import main
    from unittest.mock import MagicMock

    runtime_values = {key: False for key in main.RUNTIME_CONFIG_KEYS}
    runtime_values["scheduler_refresh_token_enabled"] = True
    schedule_values = {
        "scheduler_refresh_token_minutes": 10,
        "scheduler_refresh_today_create_task_minutes": 60,
        "scheduler_refresh_notyet_today_tasks_minutes": 30,
        "scheduler_nightly_sync_time": "01:00",
        "scheduler_archiving_time": "02:00",
    }
    scheduler = MagicMock()
    with patch.object(main, "AsyncIOScheduler", return_value=scheduler):
        main.start_scheduler(runtime_values, schedule_values)
    paused = {call.args[0] for call in scheduler.pause_job.call_args_list}
    assert paused == {main.SCHEDULER_CONFIG[key] for key in main.SCHEDULER_CONFIG if not runtime_values[key]}
    schedules = {call.kwargs["id"]: call.kwargs for call in scheduler.add_job.call_args_list}
    assert schedules["refresh_today_create_task"]["minutes"] == 60
    assert schedules["refresh_notyet_today_tasks"]["minutes"] == 30
    assert (schedules["nightly_sync"]["hour"], schedules["nightly_sync"]["minute"]) == (1, 0)


@pytest.mark.asyncio
async def test_item_reporting_failure_does_not_erase_committed_sync():
    from backend.api import job_api

    core = AsyncMock(session_factory=None)
    core.sync.return_value = outcome("task-1", "backed_up")
    with patch.object(job_api, "db_user", DBUser(task_sync=core)), \
         patch.object(job_api.job_manager, "mark_item", AsyncMock(side_effect=[None, RuntimeError("report unavailable")])):
        result = await job_api.sync_job_items([{"sendtask_uuid": "task-1"}], "job-1", orgs=None)
    assert result["job_status"] == "completed" and result["backed_up_count"] == 1
    assert result["changed_uuids"] == ["task-1"]
    assert result["notification_errors"] == {"task-1": "report unavailable"}


@pytest.mark.asyncio
async def test_job_cancellation_keeps_prior_item_commits():
    from backend.api import job_api

    core = AsyncMock(session_factory=None)
    core.sync.side_effect = [outcome("first"), asyncio.CancelledError]
    with patch.object(job_api, "db_user", DBUser(task_sync=core)), \
         patch.object(job_api.job_manager, "mark_item", AsyncMock()):
        with pytest.raises(TaskSyncCancelled) as exc:
            await job_api.sync_job_items([{"sendtask_uuid": "first"}, {"sendtask_uuid": "second"}], "job-1", orgs=None)
    assert exc.value.results.results["first"].committed


@pytest.mark.asyncio
async def test_list_cancellation_keeps_committed_results():
    service = AsyncMock()

    async def sync(*, orgs, on_result):
        await on_result(outcome("task-1"))
        raise asyncio.CancelledError

    service.sync.side_effect = sync
    with pytest.raises(TaskSyncCancelled) as exc:
        await DBUser(task_list_sync=service).sync_sendtasks(orgs=None)
    assert exc.value.results.results["task-1"].committed


@pytest.mark.asyncio
async def test_postcommit_notification_failure_does_not_change_database_result(schema_engine):
    import time
    from backend.services.task_sync_core import TaskSyncService
    from sqlalchemy import select
    from backend.repository.models import SendTask, SendLogStats

    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(100, 2)
    value.task["sendtask_id"] = "Task_(A)"
    for record in value.sendlogs:
        record["plan_time"] = record["send_time"] = int(time.time())
        record["send_res"] = "True"
    reader = AsyncMock(read_task_snapshot=AsyncMock(return_value=value))
    user = DBUser(task_sync=TaskSyncService(factory, reader))

    async def notify(message):
        assert message.endswith(r"Task\_\(A\)")
        async with factory() as session:
            assert await session.scalar(select(SendTask.sync_revision)) == 1
            assert await session.scalar(select(SendLogStats.todaysend)) == 2
        raise RuntimeError("telegram unavailable")

    with patch("backend.services.db_user.send_telegram_notification", new=notify):
        statuses = await user.refresh_sendlog_stats(["task-1"], orgs=None)
    assert statuses["task-1"] == "updated"
    assert statuses.results["task-1"].committed
    assert statuses.notification_errors == {"task-1": "telegram unavailable"}


@pytest.mark.asyncio
async def test_initialization_reports_partial_instead_of_claiming_success():
    from backend.repository.models import SendTask
    from backend.services.task_sync_entrypoints import TaskSyncIncomplete

    service = AsyncMock()
    service.sync.return_value = {"status": "partial", "changed_uuids": ["committed"], "failed_tasks": [{"sendtask_uuid": "failed"}]}
    with patch("backend.services.db_user.db_controller.get", AsyncMock(side_effect=lambda model, **kwargs: [] if model is SendTask else [SimpleNamespace()])):
        with pytest.raises(TaskSyncIncomplete) as exc:
            await DBUser(task_list_sync=service).table_initialize()
    assert exc.value.results["changed_uuids"] == ["committed"]


@pytest.mark.asyncio
async def test_initial_stats_errors_keep_successful_core_results():
    from backend.repository.models import SendTask, SendLogStats
    from backend.services.task_sync_entrypoints import TaskSyncIncomplete

    core = AsyncMock(session_factory=None)
    core.sync.side_effect = [outcome("first"), RuntimeError("remote unavailable")]

    async def get(model, *args, **kwargs):
        if model is SendLogStats:
            return []
        if model is SendTask:
            return [SimpleNamespace(sendtask_uuid="first"), SimpleNamespace(sendtask_uuid="second")]
        return [SimpleNamespace()]

    with patch("backend.services.db_user.db_controller.get", AsyncMock(side_effect=get)):
        with pytest.raises(TaskSyncIncomplete) as exc:
            await DBUser(task_sync=core).table_initialize()
    assert exc.value.results.results["first"].committed
    assert exc.value.results["second"] == "error"


@pytest.mark.asyncio
async def test_warming_tracker_keeps_partial_and_cancelled_commit_results():
    from backend import main
    from backend.services.task_sync_entrypoints import TaskSyncStatuses

    statuses = TaskSyncStatuses()
    statuses["task-1"] = "recreated"
    statuses.results["task-1"] = outcome("task-1")
    update = AsyncMock()
    with patch.object(main.db_controller, "create", AsyncMock()), patch.object(main.db_controller, "update", update):
        await main.tracked_scheduler_job("warming", AsyncMock(return_value={"job_status": "partial"}))()
        assert update.await_args.args[2]["status"] == "partial"
        with pytest.raises(TaskSyncCancelled):
            await main.tracked_scheduler_job("warming", AsyncMock(side_effect=TaskSyncCancelled(statuses)))()
    saved = update.await_args.args[2]
    assert saved["status"] == "cancelled"
    assert saved["result"]["changed_uuids"] == ["task-1"]