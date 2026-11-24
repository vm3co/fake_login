import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
import httpx
from sqlalchemy import insert, select, text, update, delete
from sqlalchemy.exc import DBAPIError

from backend.repository.models import SendTask, SendLogDetail, SendLogStats, TaskBackup, TaskBackupDetail
from backend.services.se2_task_reader import SE2TaskReader, TaskNotFound, TaskReadError, TaskSnapshot
from backend.services.task_sync import TaskSyncConflict
from backend.services.task_sync_core import TaskSyncService, TaskSyncAccessDenied
from backend.tests.repository.test_task_backup_schema import schema_engine, set_path
from backend.tests.services.test_task_backup_transfer import setup_transfer, current_counts


def snapshot(create_ut=100, count=2, *, orgs=None):
    return TaskSnapshot(
        task={"sendtask_uuid": "task-1", "sendtask_id": "Remote", "sendtask_owner_gid": orgs or ["org-1"],
              "sendtask_create_ut": create_ut, "pre_test_enable": False,
              "local_generation_id": "untrusted", "sync_revision": 999},
        metadata={"pause": False, "stop_time_new": -1, "summary": {"person_count": count}},
        sendlogs=[{
            "uuid": f"{'old' if create_ut == 100 else 'new'}-log-{number}",
            "target_email": "same@example.test", "person_info": "Test", "template_uuid": "template-1",
            "plan_time": 100, "send_time": 0, "send_res": "", "second_input_time": [999],
            **{field: [] for field in ("access_time", "access_src", "access_dev", "click_time", "click_src", "click_dev", "file_time", "file_src", "file_dev")},
        } for number in range(1, count + 1)],
        testcase={"testcase_uuid": "task-1", "testcase_id": "Remote project"},
        create_ut=create_ut, sendlog_type="test",
    )


def service(factory, value=None, error=None, **kwargs):
    reader = AsyncMock()
    reader.read_task_snapshot = AsyncMock(return_value=value, side_effect=error)
    return TaskSyncService(factory, reader, **kwargs)


@pytest.mark.asyncio
async def test_same_version_preserves_local_events_and_uses_live_rows_for_stats(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    async with factory() as session:
        async with session.begin():
            await session.execute(update(SendLogDetail).values(second_input_src=["ip-1", "ip-2"]))
    core = service(factory, snapshot())
    for revision in (1, 2):
        result = await core.sync("task-1", orgs=["org-1"])
        assert result.status == "updated" and result.committed
        assert result.revision == revision and result.generation != "untrusted"
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    async with factory() as session:
        assert (await session.scalars(select(SendLogDetail.second_input_time))).all() == [[70, 80], [70, 80]]
        assert await session.scalar(select(SendLogStats.totalplanned)) == 2
        assert await session.scalar(select(SendLogStats.totaltriggered)) == 2
        assert await session.scalar(select(SendTask.sendtask_id)) == "Remote"


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 5])
async def test_recreation_atomically_replaces_rows_and_keeps_backup(schema_engine, count):
    factory, _, _ = await setup_transfer(schema_engine)
    core = service(factory, snapshot(200, count))
    result = await core.sync("task-1", orgs=None)
    assert result.status == "recreated" and result.backup_id and result.backups_changed
    assert await current_counts(factory) == (1, count, 1, 1, 2)
    async with factory() as session:
        backup = await session.scalar(select(TaskBackup))
        assert backup.recreated_detected_at is not None
        assert backup.task_snapshot["sendtask_create_ut"] == 100
        assert await session.scalar(select(SendTask.local_generation_id)) != backup.source_local_generation_id
        assert await session.scalar(select(SendLogStats.totalplanned)) == count
        assert all(value is None for value in (await session.scalars(select(SendLogDetail.second_input_time))).all())


@pytest.mark.asyncio
async def test_missing_then_rebuilt_import_does_not_merge_history(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    result = await service(factory, error=TaskNotFound("missing")).sync("task-1", orgs=["org-1"])
    assert result.status == "backed_up" and result.backup_id
    assert await current_counts(factory) == (0, 0, 0, 1, 2)
    again = await service(factory, error=TaskNotFound("missing")).sync("task-1", orgs=None)
    assert again.status == "unchanged" and again.changed_uuids == ()
    result = await service(factory, snapshot(200, 5)).sync("task-1", orgs=["org-1"])
    assert result.status == "added"
    assert await current_counts(factory) == (1, 5, 1, 1, 2)


@pytest.mark.asyncio
async def test_read_failure_leaves_everything_untouched(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    with pytest.raises(TaskReadError):
        await service(factory, error=TaskReadError("page_failed")).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_stale_prepared_success_and_missing_never_apply(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    core = service(factory, snapshot())
    old_success = await core.prepare("task-1", orgs=None)
    old_missing = await service(factory, error=TaskNotFound("missing")).prepare("task-1", orgs=None)
    await service(factory, snapshot(200, 5)).sync("task-1", orgs=None)
    for prepared in (old_success, old_missing):
        with pytest.raises(TaskSyncConflict):
            await core.apply(prepared)
    assert await current_counts(factory) == (1, 5, 1, 1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,remote_org", [([], ["org-1"]), (["other"], ["org-1"]), (["org-1"], ["other"])])
async def test_local_and_remote_scope_are_enforced(schema_engine, scope, remote_org):
    factory, _, _ = await setup_transfer(schema_engine)
    core = service(factory, snapshot(orgs=remote_org))
    with pytest.raises(TaskSyncAccessDenied):
        await core.sync("task-1", orgs=scope)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    if scope != ["org-1"]:
        core.reader.read_task_snapshot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, {}, [], "missing"])
async def test_invalid_reader_result_never_implies_deleted(schema_engine, value):
    factory, _, _ = await setup_transfer(schema_engine)
    with pytest.raises(TaskReadError, match="invalid_snapshot"):
        await service(factory, value).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["send_log_details", "sendlog_stats"])
async def test_new_detail_or_stats_failure_rolls_back_old_version_and_backup(schema_engine, table):
    factory, engine, schema = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.execute(text("CREATE FUNCTION fail_core() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected core failure'; END $$"))
        await conn.execute(text(f"CREATE TRIGGER fail_core BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION fail_core()"))
    with pytest.raises(DBAPIError):
        await service(factory, snapshot(200, 5)).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    async with factory() as session:
        assert await session.scalar(select(SendTask.sendtask_create_ut)) == 100
        assert await session.scalar(select(SendTask.sync_revision)) == 0
        assert (await session.scalars(select(SendLogDetail.second_input_time))).all() == [[70, 80], [70, 80]]


@pytest.mark.asyncio
async def test_cancel_during_stats_rolls_back_recreation(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)

    def cancel_stats(records):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await service(factory, snapshot(200), stats_calculator=cancel_stats).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    assert (await service(factory, snapshot()).sync("task-1", orgs=None)).status == "updated"


@pytest.mark.asyncio
async def test_remote_missing_details_are_retained_in_same_version(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    result = await service(factory, snapshot(100, 1)).sync("task-1", orgs=None)
    assert result.status == "updated"
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    async with factory() as session:
        assert await session.scalar(select(SendLogStats.totalplanned)) == 2


@pytest.mark.asyncio
async def test_other_task_log_uuid_cannot_be_stolen(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(SendTask).values(sendtask_uuid="other-task", sendtask_id="Other", sendtask_owner_gid=["org-2"]))
        await conn.execute(insert(SendLogDetail).values(uuid="new-log-1", sendtask_uuid="other-task", person_info="Untouched"))
    with pytest.raises(TaskSyncConflict, match="another task"):
        await service(factory, snapshot(200, 5)).sync("task-1", orgs=None)
    assert await current_counts(factory) == (2, 3, 1, 0, 0)
    async with factory() as session:
        assert await session.scalar(select(SendLogDetail.person_info).where(SendLogDetail.uuid == "new-log-1")) == "Untouched"


@pytest.mark.asyncio
@pytest.mark.parametrize("local_time", [None, 0, -1])
async def test_invalid_local_version_preserves_data(schema_engine, local_time):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(sendtask_create_ut=local_time))
    with pytest.raises(TaskReadError):
        await service(factory, snapshot(200)).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_fresh_import_does_not_inherit_earlier_testcase_or_local_fields(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(alert_content="Old alert", is_archived=True))
    result = await service(factory, snapshot(200, 5)).sync("task-1", orgs=None)
    async with factory() as session:
        current = await session.scalar(select(SendTask))
        assert current.alert_content is None
        assert current.is_archived is False
        assert current.local_generation_id == result.generation
        assert current.sync_revision == 0
        assert (await session.scalar(select(TaskBackup.task_snapshot)))["alert_content"] == "Old alert"


@pytest.mark.asyncio
async def test_empty_same_version_and_null_legacy_timestamps_do_not_erase_rows(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendLogDetail).values(plan_time=None, send_time=None))
    await service(factory, snapshot(100, 0)).sync("task-1", orgs=None)
    async with factory() as session:
        assert await session.scalar(select(SendLogStats.totalplanned)) == 2
        assert await session.scalar(select(SendLogStats.totalsend)) == 0
        assert (await session.scalars(select(SendLogDetail.plan_time))).all() == [None, None]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, ["org-1"]])
async def test_backup_observation_respects_older_version_organizations(schema_engine, scope):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        for generation, owner in (("old-a", ["org-1"]), ("old-b", ["org-2"]), ("same-version", ["org-1"])):
            await conn.execute(insert(TaskBackup).values(
                source_task_uuid="task-1", source_create_ut=100 if generation == "same-version" else 50,
                source_local_generation_id=generation, sendtask_id="History", owner_gids=owner,
                reason="manual_reload", task_snapshot={"immutable": True},
            ))
    await service(factory, snapshot()).sync("task-1", orgs=scope)
    async with factory() as session:
        backups = (await session.scalars(select(TaskBackup))).all()
        for backup in backups:
            assert backup.task_snapshot == {"immutable": True}
            if scope is not None and backup.owner_gids == ["org-2"]:
                assert backup.latest_remote_status == "unchecked"
                assert backup.recreated_detected_at is None
            else:
                assert backup.latest_remote_status == "present"
                assert (backup.recreated_detected_at is not None) == (backup.source_create_ut != 100)


@pytest.mark.asyncio
async def test_prepare_is_read_only_and_remote_errors_do_not_touch_history(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    core = service(factory, snapshot(200, 5))
    await core.prepare("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_two_prepared_new_imports_cannot_both_commit(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(delete(SendTask))
        await conn.execute(delete(SendLogStats))
    core = service(factory, snapshot(200, 5))
    prepared = await core.prepare("task-1", orgs=None)
    results = await asyncio.gather(core.apply(prepared), core.apply(deepcopy(prepared)), return_exceptions=True)
    assert sum(isinstance(value, TaskSyncConflict) for value in results) == 1
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert await current_counts(factory) == (1, 5, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version", "duplicate", "mode", "event", "taskcase"])
async def test_invalid_prepared_snapshot_is_revalidated_before_any_write(schema_engine, change):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(200)
    if change == "version":
        value.task["sendtask_create_ut"] = None
    elif change == "duplicate":
        value.sendlogs[1]["uuid"] = value.sendlogs[0]["uuid"]
    elif change == "mode":
        value = replace(value, sendlog_type="pretest")
    elif change == "event":
        del value.sendlogs[0]["access_time"]
    else:
        value = replace(value, testcase={"testcase_uuid": "other-task"})
    with pytest.raises(TaskReadError):
        await service(factory, value).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_numeric_strings_are_same_version_and_stop_time_is_normalized(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot("100")
    value.metadata["stop_time_new"] = "-1"
    result = await service(factory, value).sync("task-1", orgs=None)
    assert result.status == "updated"
    assert result.backup_id is None
    async with factory() as session:
        assert await session.scalar(select(SendTask.stop_time_new)) == -1
        assert await session.scalar(select(SendTask.sendtask_create_ut)) == 100


@pytest.mark.asyncio
async def test_old_three_people_new_five_people_have_separate_generations(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(insert(SendLogDetail).values(
            uuid="old-log-3", sendtask_uuid="task-1", plan_time=100, send_time=0,
            second_input_info=["third historic event"],
        ))
        await conn.execute(update(SendLogStats).values(totalplanned=3))
    await service(factory, snapshot(200, 5)).sync("task-1", orgs=None)
    assert await current_counts(factory) == (1, 5, 1, 1, 3)
    async with factory() as session:
        assert await session.scalar(select(SendLogStats.totalplanned)) == 5
        assert (await session.scalar(select(TaskBackup.stats_snapshot)))["totalplanned"] == 3
        assert await session.scalar(select(TaskBackupDetail.second_input_info).where(
            TaskBackupDetail.uuid == "old-log-3",
        )) == ["third historic event"]


@pytest.mark.asyncio
async def test_missing_without_local_ownership_is_not_authorized_for_scoped_user(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(delete(SendTask))
        await conn.execute(delete(SendLogStats))
    with pytest.raises(TaskSyncAccessDenied):
        await service(factory, error=TaskNotFound("missing")).sync("task-1", orgs=["org-1"])
    assert await current_counts(factory) == (0, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_prepare_and_apply_both_validate_ownership(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    core = service(factory, snapshot(200))
    prepared = await core.prepare("task-1", orgs=["org-1"])
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(sendtask_owner_gid=["org-2"]))
    with pytest.raises(TaskSyncAccessDenied):
        await core.apply(prepared)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_strict_reader_and_core_complete_pipeline(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(200, 5)
    requests = []

    def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("get_sendtask"):
            return httpx.Response(200, json={"data": value.task, "metadata": value.metadata})
        if request.url.path.endswith("get_testcase"):
            return httpx.Response(200, json={"data": value.testcase})
        return httpx.Response(200, json={"data": value.sendlogs, "metadata": {"total": 5}})

    reader = SE2TaskReader("https://se2.test", lambda: {}, False, transport=httpx.MockTransport(handler))
    result = await TaskSyncService(factory, reader).sync("task-1", orgs=None)
    assert result.committed and result.status == "recreated"
    assert [path.rsplit("/", 1)[-1] for path, payload in requests] == [
        "get_sendtask", "get_sendlog", "get_testcase", "get_sendtask",
    ]
    assert await current_counts(factory) == (1, 5, 1, 1, 2)


@pytest.mark.asyncio
async def test_missing_after_recreated_observation_does_not_erase_proof(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    await service(factory, snapshot(200)).sync("task-1", orgs=None)
    async with factory() as session:
        first = await session.scalar(select(TaskBackup))
        first_id, proof = first.backup_id, first.recreated_detected_at
    await service(factory, error=TaskNotFound("missing")).sync("task-1", orgs=None)
    async with factory() as session:
        first = await session.get(TaskBackup, first_id)
        assert first.recreated_detected_at == proof
        assert first.task_snapshot["sendtask_create_ut"] == 100


@pytest.mark.asyncio
async def test_pretest_uses_known_local_mode_without_error_fallback(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(pre_test_enable=True))
    value = snapshot()
    value.task["pre_test_enable"] = True
    value = replace(value, sendlog_type="pretest")
    core = service(factory, value)
    await core.sync("task-1", orgs=None)
    core.reader.read_task_snapshot.assert_awaited_once_with("task-1", sendlog_type="pretest")
    failure = service(factory, error=TaskReadError("pretest_not_found_unverified"))
    with pytest.raises(TaskReadError):
        await failure.sync("task-1", orgs=None)
    failure.reader.read_task_snapshot.assert_awaited_once_with("task-1", sendlog_type="pretest")
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
async def test_new_pretest_import_accepts_explicit_trusted_mode(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(delete(SendTask))
        await conn.execute(delete(SendLogStats))
    value = snapshot()
    value.task["pre_test_enable"] = True
    core = service(factory, replace(value, sendlog_type="pretest"))
    result = await core.sync("task-1", orgs=["org-1"], sendlog_type="pretest")
    assert result.status == "added"
    core.reader.read_task_snapshot.assert_awaited_once_with("task-1", sendlog_type="pretest")


@pytest.mark.asyncio
async def test_apply_revalidates_modified_prepared_payload(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    core = service(factory, snapshot(200))
    prepared = await core.prepare("task-1", orgs=["org-1"])
    prepared.snapshot.task["sendtask_owner_gid"] = ["org-2"]
    with pytest.raises(TaskSyncAccessDenied):
        await core.apply(prepared)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    prepared = await core.prepare("task-1", orgs=None)
    prepared.snapshot.sendlogs[0]["plan_time"] = "invalid"
    with pytest.raises(TaskReadError):
        await core.apply(prepared)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)