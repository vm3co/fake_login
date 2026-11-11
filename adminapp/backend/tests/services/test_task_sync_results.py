import json
from unittest.mock import AsyncMock

import pytest

from backend.services.task_sync_core import TaskSyncResult
from backend.services.task_sync_entrypoints import TaskSyncStatuses, summarize_task_sync
from backend.services.task_sync_progress import TaskSyncProgress, merge_job_results, report_commit, track_task_sync
from backend.tests.repository.test_task_backup_schema import schema_engine
from unittest.mock import patch
import asyncio


def test_summary_serializes_commits_versions_transitions_conflicts_and_warnings():
    statuses = TaskSyncStatuses()
    statuses.update({"current": "recreated", "missing": "backed_up", "failed": "error"})
    statuses.results["current"] = TaskSyncResult(
        "recreated", "current", "generation-2", 0, "backup-1", True, ("current",), True, "unarchived",
    )
    statuses.results["missing"] = TaskSyncResult("backed_up", "missing", None, None, "backup-2", True, ("missing",), True)
    statuses.errors["failed"] = "stale preparation"
    statuses.retryable_errors["failed"] = True
    statuses.notification_errors["current"] = "redis unavailable"
    summary = json.loads(json.dumps(summarize_task_sync(statuses, [])))
    assert summary["job_status"] == "partial"
    assert summary["recreated_count"] == summary["backed_up_count"] == summary["unarchived_count"] == 1
    assert summary["conflict_count"] == 1 and summary["failed_tasks"][0]["retryable"]
    assert summary["changed_uuids"] == ["current", "missing"] and summary["reload_list"]
    assert summary["sync_results"]["current"]["generation"] == "generation-2"
    assert summary["sync_results"]["missing"]["generation"] is None
    assert summary["warnings"][0]["stage"] == "post_commit"
    assert "deleted_count" not in summary


@pytest.mark.asyncio
async def test_each_commit_is_saved_and_final_error_cannot_clear_progress():
    save = AsyncMock()
    progress = TaskSyncProgress(save)
    first = TaskSyncResult("backed_up", "first", None, None, "backup-1", True, ("first",), True)
    second = TaskSyncResult("reloaded", "second", "new", 0, "backup-2", True, ("second",), True)
    with track_task_sync(progress):
        await report_commit(first)
        assert save.await_count == 1
        await report_commit(second)
    merged = merge_job_results(progress.result, {"job_status": "failed", "failed_count": 1})
    assert merged["changed_uuids"] == ["first", "second"] and merged["backups_changed"]
    assert merged["backed_up_count"] == merged["reloaded_count"] == 1
    assert merged["job_status"] == "failed"
    assert save.await_count == 2
    assert json.loads(json.dumps(merged))["sync_results"]["second"]["committed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_queue_keeps_commits_when_handler_fails_or_cancels(cancel):
    from backend.services.job_queue import JobQueue

    queue = JobQueue()
    committed = TaskSyncResult("updated", "task-1", "generation", 1, None, True, ("task-1",), False)

    async def handler(job_id):
        await report_commit(committed)
        raise asyncio.CancelledError if cancel else RuntimeError("next task failed")

    queue.register("sync", handler)
    with patch.object(queue, "_set_running", AsyncMock()), \
         patch.object(queue, "save_progress", AsyncMock()) as save, \
         patch.object(queue, "_finish", AsyncMock()) as finish:
        await queue._run_claimed("job-1", "sync")
    assert save.await_count == 1
    assert finish.await_args.args[1] == ("cancelled" if cancel else "failed")
    assert finish.await_args.kwargs["result"]["changed_uuids"] == ["task-1"]


@pytest.mark.asyncio
async def test_progress_and_finish_persist_without_clearing_commits(schema_engine):
    from sqlalchemy import insert, select
    from backend.repository.models import JobRun, JobRunItem
    from backend.services.job_queue import JobQueue
    from backend.tests.services.test_task_backup_transfer import setup_transfer

    factory, engine, _ = await setup_transfer(schema_engine)
    queue = JobQueue()
    async with engine.begin() as conn:
        await conn.execute(insert(JobRun).values(job_id="job-1", source="manual", owner_username="user-a",
                                                job_type="sync", status="running", claimed_by=queue.worker_id))
        await conn.execute(insert(JobRunItem).values(job_id="job-1", sendtask_uuid="task-1", sendtask_id="Task", status="running"))
    statuses = TaskSyncStatuses()
    statuses["task-1"] = "backed_up"
    statuses.results["task-1"] = TaskSyncResult("backed_up", "task-1", None, None, "backup", True, ("task-1",), True)
    with patch("backend.services.job_queue.async_session", factory):
        await queue.save_progress("job-1", summarize_task_sync(statuses, []))
        async with factory() as session:
            assert (await session.scalar(select(JobRun.result)))["changed_uuids"] == ["task-1"]
        await queue._finish("job-1", "cancelled")
    async with factory() as session:
        job = await session.scalar(select(JobRun))
        assert job.status == "cancelled" and job.result["backed_up_count"] == 1
        assert job.result["sync_results"]["task-1"]["committed"]
        item = await session.scalar(select(JobRunItem))
        assert item.status == "completed" and item.reason == "backed_up"


def test_legacy_job_result_keeps_fields_and_safe_refresh_defaults():
    assert merge_job_results({}, {"updated": 1}) == {
        "updated": 1, "changed_uuids": [], "backups_changed": False, "reload_list": False, "warnings": [],
    }


@pytest.mark.asyncio
async def test_batch_preserves_current_commit_attached_to_cancellation():
    from backend.services.task_sync_entrypoints import TaskSyncCancelled, sync_task_batch

    committed = TaskSyncStatuses()
    committed["current"] = "reloaded"
    committed.results["current"] = TaskSyncResult("reloaded", "current", "new", 0, "backup", True, ("current",), True)
    first = TaskSyncResult("updated", "first", "generation", 1, None, True, ("first",), False)
    core = AsyncMock(sync=AsyncMock(side_effect=[first, TaskSyncCancelled(committed)]))
    with pytest.raises(TaskSyncCancelled) as exc:
        await sync_task_batch(core, ["first", "current"], orgs=None)
    assert set(exc.value.results.results) == {"first", "current"}


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_real_queue_saves_first_database_commit_before_next_failure(schema_engine, cancel):
    from sqlalchemy import insert, select
    from backend.repository.models import JobRun
    from backend.services.job_queue import JobQueue
    from backend.services.task_sync_core import TaskSyncService
    from backend.tests.services.test_task_backup_transfer import setup_transfer
    from backend.tests.services.test_task_sync_core import snapshot

    factory, engine, _ = await setup_transfer(schema_engine)
    queue = JobQueue()
    async with engine.begin() as conn:
        await conn.execute(insert(JobRun).values(job_id="job-1", source="scheduler", owner_username="system",
                                                job_type="list", status="claiming", claimed_by=queue.worker_id))
    redis = AsyncMock()
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=snapshot(200, 5))))

    async def handler(job_id):
        await core.sync("task-1", orgs=None)
        async with factory() as session:
            saved = await session.scalar(select(JobRun.result))
            assert saved["sync_results"]["task-1"]["generation"]
            assert saved["recreated_count"] == 1
        raise asyncio.CancelledError if cancel else RuntimeError("later failure")

    queue.register("list", handler)
    with patch("backend.services.job_queue.async_session", factory), \
         patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(return_value=redis)):
        await queue._run_claimed("job-1", "list")
    async with factory() as session:
        job = await session.scalar(select(JobRun))
        assert job.status == ("cancelled" if cancel else "failed")
        assert job.result["changed_uuids"] == ["task-1"]
        assert job.result["backups_changed"] and job.result["reload_list"]


@pytest.mark.asyncio
async def test_cancel_during_postcommit_invalidation_still_saves_committed_result(schema_engine):
    from backend.services.task_sync_core import TaskSyncService
    from backend.services.task_sync_entrypoints import TaskSyncCancelled
    from backend.tests.services.test_task_backup_transfer import setup_transfer
    from backend.tests.services.test_task_sync_core import snapshot

    factory, _, _ = await setup_transfer(schema_engine)
    entered = asyncio.Event()
    release = asyncio.Event()
    save = AsyncMock()
    progress = TaskSyncProgress(save)

    async def invalidate(*keys):
        entered.set()
        await release.wait()

    redis = AsyncMock(delete=AsyncMock(side_effect=invalidate))
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=snapshot())))
    with patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(return_value=redis)):
        with track_task_sync(progress):
            task = asyncio.create_task(core.sync("task-1", orgs=None))
            await entered.wait()
            task.cancel()
            release.set()
            with pytest.raises(TaskSyncCancelled) as exc:
                await task
    assert exc.value.results.results["task-1"].committed
    assert progress.result["changed_uuids"] == ["task-1"] and save.await_count == 1


@pytest.mark.asyncio
async def test_warning_alone_does_not_change_success_or_lose_progress():
    from backend.services.task_sync_entrypoints import sync_task_batch

    save = AsyncMock()
    progress = TaskSyncProgress(save)
    committed = TaskSyncResult("updated", "task-1", "generation", 1, None, True, ("task-1",), False)
    core = AsyncMock(sync=AsyncMock(return_value=committed))
    with track_task_sync(progress):
        statuses = await sync_task_batch(core, ["task-1"], orgs=None, on_result=AsyncMock(side_effect=RuntimeError("telegram down")))
    assert summarize_task_sync(statuses, [])["job_status"] == "completed"
    assert progress.result["warnings"][0]["stage"] == "notification"


@pytest.mark.asyncio
@pytest.mark.parametrize("fails_twice", [False, True])
async def test_cache_invalidation_retries_twice_without_changing_commit(fails_twice):
    redis = AsyncMock()
    redis.delete.side_effect = [RuntimeError("first"), RuntimeError("second") if fails_twice else 1]
    result = TaskSyncResult("reloaded", "task-1", "new", 0, "backup", True, ("task-1",), True, replayed=True)
    with patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(return_value=redis)):
        final = await report_commit(result, invalidate=True)
    assert final.committed and final.status == "reloaded" and final.replayed
    assert redis.delete.await_count == 2
    assert bool(final.warnings) is fails_twice
    if fails_twice:
        assert final.warnings[0]["attempts"] == 2


@pytest.mark.asyncio
async def test_progress_storage_failure_is_warning_not_database_rollback():
    progress = TaskSyncProgress(AsyncMock(side_effect=RuntimeError("job storage unavailable")))
    result = TaskSyncResult("updated", "task-1", "gen", 1, None, True, ("task-1",), False)
    with track_task_sync(progress):
        final = await report_commit(result)
    assert final.committed and final.warnings[0]["stage"] == "progress"
    assert progress.result["changed_uuids"] == ["task-1"]


def test_list_failure_without_status_map_is_preserved_and_unfinished_are_distinct():
    statuses = TaskSyncStatuses()
    statuses["committed"] = "updated"
    statuses.results["committed"] = TaskSyncResult("updated", "committed", "gen", 1, None, True, ("committed",), False)
    first = merge_job_results(summarize_task_sync(statuses, []), {
        "target_tasks": [{"sendtask_uuid": task_uuid} for task_uuid in ("committed", "failed", "pending")],
    })
    merged = merge_job_results(first, {"failed_tasks": [{"sendtask_uuid": "failed", "reason": "http_error"}]})
    assert merged["failed_count"] == 1
    assert merged["unfinished_tasks"] == [{"sendtask_uuid": "pending"}]
    assert merged["changed_uuids"] == ["committed"]


def test_merge_latest_task_outcome_wins_but_other_failures_still_make_partial():
    failed = {"sync_statuses": {"retry": "error", "other": "error"}, "failed_tasks": [
        {"sendtask_uuid": task_uuid, "reason": "unavailable"} for task_uuid in ("retry", "other")
    ]}
    statuses = TaskSyncStatuses()
    statuses["retry"] = "updated"
    statuses.results["retry"] = TaskSyncResult("updated", "retry", "gen", 1, None, True, ("retry",), False)
    merged = merge_job_results(failed, summarize_task_sync(statuses, []))
    assert merged["sync_statuses"] == {"retry": "updated", "other": "error"}
    assert merged["failed_count"] == 1 and merged["failed_tasks"][0]["sendtask_uuid"] == "other"
    assert merged["job_status"] == "partial"


def test_list_notification_errors_merge_without_losing_committed_results():
    statuses = TaskSyncStatuses()
    statuses["task-1"] = "updated"
    statuses.results["task-1"] = TaskSyncResult("updated", "task-1", "gen", 1, None, True, ("task-1",), False)
    merged = merge_job_results(summarize_task_sync(statuses, []), {
        "notification_errors": [{"sendtask_uuid": "task-1", "reason": "notification unavailable"}],
    })
    assert merged["job_status"] == "completed"
    assert merged["notification_errors"] == {"task-1": "notification unavailable"}
    assert merged["changed_uuids"] == ["task-1"]
    assert merged["warnings"][0]["message"] == "notification unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "transport"])
async def test_real_notification_failure_returns_status_and_commit_keeps_warning(schema_engine, failure):
    import httpx
    import time
    from backend.services import notification_manager
    from backend.services.db_user import DBUser
    from backend.services.task_sync_core import TaskSyncService
    from backend.tests.services.test_task_backup_transfer import setup_transfer
    from backend.tests.services.test_task_sync_core import snapshot

    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot()
    for record in value.sendlogs:
        record["plan_time"] = record["send_time"] = int(time.time())
        record["send_res"] = "True"
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=value)))
    client = AsyncMock()
    if failure == "http":
        client.post.return_value = httpx.Response(500, text="notification unavailable")
    else:
        client.post.side_effect = httpx.ConnectError("notification unavailable")
    context = AsyncMock()
    context.__aenter__.return_value = client
    with patch.object(notification_manager, "BOT_TOKEN", "test-token"), \
         patch.object(notification_manager, "CHAT_ID", "test-chat"), \
         patch.object(notification_manager.httpx, "AsyncClient", return_value=context), \
         patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(return_value=AsyncMock())):
        statuses = await DBUser(task_sync=core).sync_tasks(["task-1"], orgs=None)
    summary = summarize_task_sync(statuses, [])
    assert summary["job_status"] == "completed"
    assert summary["sync_results"]["task-1"]["committed"]
    assert summary["warnings"][-1]["message"] == "Telegram notification delivery failed"


@pytest.mark.asyncio
async def test_job_manager_keeps_committed_item_when_task_raises_cancelled_result():
    from backend.services.job_manager import JobManager
    from backend.services.job_queue import job_queue
    from backend.services.task_sync_entrypoints import TaskSyncCancelled

    manager = JobManager()
    statuses = TaskSyncStatuses()
    statuses["task-1"] = "backed_up"
    statuses.results["task-1"] = TaskSyncResult("backed_up", "task-1", None, None, "backup", True, ("task-1",), True)

    async def task_func(**kwargs):
        raise TaskSyncCancelled(statuses)

    registered = {}
    update = AsyncMock()
    with patch("backend.services.job_manager.db_controller.create", AsyncMock()), \
         patch("backend.services.job_manager.db_controller.update", update), \
         patch.object(job_queue, "register_job", lambda job_id, handler: registered.update({job_id: handler})), \
         patch.object(job_queue, "wake"):
        admission = await manager.start_job("user-a", "sync", task_func, items=[{"sendtask_uuid": "task-1", "sendtask_id": "Task"}])
        with pytest.raises(TaskSyncCancelled):
            await registered[admission["job_id"]](admission["job_id"])
    result = manager.jobs[admission["job_id"]]
    assert result["status"] == "cancelled" and result["result"]["backed_up_count"] == 1
    assert any(call.args[2].get("reason") == "backed_up" for call in update.await_args_list)


@pytest.mark.asyncio
async def test_queue_decides_terminal_status_after_merging_committed_progress():
    from backend.services.job_queue import JobQueue
    from backend.services.task_sync_progress import report_outcomes

    queue = JobQueue()

    async def handler(job_id):
        await report_commit(TaskSyncResult("updated", "done", "gen", 1, None, True, ("done",), False))
        await report_outcomes({"failed_tasks": [{"sendtask_uuid": "failed", "reason": "read_error"}]})
        return {"job_status": "completed"}

    queue.register("sync", handler)
    with patch.object(queue, "_set_running", AsyncMock()), \
         patch.object(queue, "save_progress", AsyncMock()), \
         patch.object(queue, "_finish", AsyncMock()) as finish:
        await queue._run_claimed("job-1", "sync")
    assert finish.await_args.args[1] == "partial"
    assert finish.await_args.kwargs["result"]["failed_count"] == 1


@pytest.mark.asyncio
async def test_queue_finalizes_committed_and_unfinished_items_separately(schema_engine):
    from sqlalchemy import insert, select
    from backend.repository.models import JobRun, JobRunItem
    from backend.services.job_queue import JobQueue
    from backend.tests.services.test_task_backup_transfer import setup_transfer

    factory, engine, _ = await setup_transfer(schema_engine)
    queue = JobQueue()
    async with engine.begin() as conn:
        await conn.execute(insert(JobRun).values(job_id="job-1", source="manual", owner_username="user-a",
                                                job_type="sync", status="running", claimed_by=queue.worker_id))
        for task_uuid in ("done", "pending"):
            await conn.execute(insert(JobRunItem).values(job_id="job-1", sendtask_uuid=task_uuid, sendtask_id=task_uuid, status="running"))
    statuses = TaskSyncStatuses()
    statuses["done"] = "backed_up"
    statuses.results["done"] = TaskSyncResult("backed_up", "done", None, None, "backup", True, ("done",), True)
    result = merge_job_results(summarize_task_sync(statuses, []), {
        "target_tasks": [{"sendtask_uuid": task_uuid} for task_uuid in ("done", "pending")],
    })
    with patch("backend.services.job_queue.async_session", factory):
        await queue._finish("job-1", "cancelled", result)
    async with factory() as session:
        items = (await session.scalars(select(JobRunItem).order_by(JobRunItem.sendtask_uuid))).all()
        assert [(item.status, item.reason) for item in items] == [("completed", "backed_up"), ("cancelled", "cancelled")]
        saved = await session.scalar(select(JobRun.result))
        assert saved["job_status"] == "cancelled" and saved["unfinished_count"] == 1