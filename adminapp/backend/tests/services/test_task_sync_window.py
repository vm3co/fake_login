from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch
from sqlalchemy import update, select
from backend.repository.models import SendTask
from backend.services.task_sync import TaskSyncConflict
from backend.services.task_sync_entrypoints import TaskSyncStatuses, summarize_task_sync

import pytest

from backend.services.se2_task_reader import TaskNotFound, TaskReadError
from backend.services.task_sync_core import TaskSyncService, TaskReloadIntent
from backend.services.task_sync_window import automatic_sync, automatic_task_sync, sync_window_closed
from backend.tests.repository.test_task_backup_schema import schema_engine
from backend.tests.services.test_task_backup_transfer import setup_transfer, current_counts
from backend.tests.services.test_task_sync_core import snapshot


def timestamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=ZoneInfo('Asia/Taipei')).timestamp())


@pytest.mark.parametrize('now,closed', [
    ('2026-11-19T16:00:00', False), ('2026-11-20T01:00:00', False),
    ('2026-11-20T23:59:59', False), ('2026-11-21T00:00:00', True),
    ('2026-11-21T01:00:00', True),
])
def test_taipei_calendar_window(now, closed):
    assert sync_window_closed({'pre_test_enable': False, 'test_end_ut': timestamp('2026-11-19T15:00:00')},
        {'stop_time_new': -1}, timestamp(now)) is closed


def test_stop_pretest_unknown_and_invalid_end():
    now = timestamp('2026-11-21T01:00:00')
    task = {'pre_test_enable': True, 'pre_test_end_ut': timestamp('2026-11-22T15:00:00'), 'test_end_ut': 100}
    assert not sync_window_closed(task, {'stop_time_new': -1}, now)
    assert sync_window_closed(task, {'stop_time_new': 100}, now)
    for end in (None, 0, -1):
        assert not sync_window_closed({'pre_test_enable': False, 'test_end_ut': end}, {'stop_time_new': -1}, now)
    with pytest.raises(TaskReadError):
        sync_window_closed({'pre_test_enable': False, 'test_end_ut': 'broken'}, {'stop_time_new': -1}, now)


@pytest.mark.asyncio
async def test_automatic_closed_window_skips_download_stats_and_manual_still_updates(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot()
    value.task['test_end_ut'] = 100
    reader = AsyncMock()
    reader.read_sendtask.return_value = {'data': value.task, 'metadata': value.metadata}
    reader.read_task_snapshot.return_value = value
    calculate = AsyncMock(side_effect=AssertionError('No stats calculation'))
    core = TaskSyncService(factory, reader, stats_calculator=calculate)
    token = automatic_sync.set(True)
    try:
        result = await core.sync('task-1', orgs=['org-1'])
    finally:
        automatic_sync.reset(token)
    assert result.status == 'unchanged' and result.skip_reason == 'automatic_sync_window_closed'
    assert result.revision == 0 and result.changed_uuids == ()
    async with factory() as session:
        assert await session.scalar(select(SendTask.sync_revision)) == 0
    statuses = TaskSyncStatuses()
    statuses['task-1'] = result.status
    statuses.results['task-1'] = result
    summary = summarize_task_sync(statuses, [])
    assert summary['window_skipped_count'] == 1 and summary['updated_count'] == 0
    reader.read_task_snapshot.assert_not_awaited()
    calculate.assert_not_called()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    manual = TaskSyncService(factory, reader)
    assert (await manual.sync('task-1', orgs=['org-1'])).status == 'updated'
    reader.read_task_snapshot.assert_awaited_once()
    token = automatic_sync.set(True)
    try:
        reloaded = await manual.sync('task-1', orgs=None,
            reload_intent=TaskReloadIntent('window-reload', 'tester', result.generation))
    finally:
        automatic_sync.reset(token)
    assert reloaded.status == 'reloaded'
    assert reader.read_task_snapshot.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('now,downloads', [('2026-11-20T01:00:00', 1), ('2026-11-21T01:00:00', 0)])
async def test_actual_download_matches_user_example(schema_engine, now, downloads):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot()
    value.task['test_end_ut'] = timestamp('2026-11-19T15:00:00')
    reader = AsyncMock()
    reader.read_sendtask.return_value = {'data': value.task, 'metadata': value.metadata}
    reader.read_task_snapshot.return_value = value
    token = automatic_sync.set(True)
    try:
        with patch('backend.services.task_sync_core.time.time', return_value=timestamp(now)):
            await TaskSyncService(factory, reader).sync('task-1', orgs=None)
    finally:
        automatic_sync.reset(token)
    assert reader.read_task_snapshot.await_count == downloads


@pytest.mark.asyncio
async def test_closed_window_can_archive_without_touching_details_or_stats(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot()
    value.task['test_end_ut'] = 100
    reader = AsyncMock()
    reader.read_sendtask.return_value = {'data': value.task, 'metadata': value.metadata}
    token = automatic_sync.set(True)
    try:
        result = await TaskSyncService(factory, reader).sync('task-1', orgs=None, archive_at=2000000)
    finally:
        automatic_sync.reset(token)
    assert result.archive_transition == 'archived' and result.revision == 1
    assert result.changed_uuids == ('task-1',)
    async with factory() as session:
        assert await session.scalar(select(SendTask.sync_revision)) == 1
    reader.read_task_snapshot.assert_not_awaited()
    assert await current_counts(factory) == (1, 2, 1, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['extended', 'recreated', 'missing', 'error'])
async def test_automatic_still_handles_extension_recreation_missing_and_error(schema_engine, case):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot(200 if case == 'recreated' else 100, 5)
    value.task['test_end_ut'] = timestamp('2099-11-19T15:00:00') if case == 'extended' else 100
    reader = AsyncMock()
    reader.read_sendtask.return_value = {'data': value.task, 'metadata': value.metadata}
    reader.read_task_snapshot.return_value = value
    if case in {'missing', 'error'}:
        error = TaskNotFound('missing') if case == 'missing' else TaskReadError('broken_metadata')
        reader.read_sendtask.side_effect = error
    core = TaskSyncService(factory, reader)
    token = automatic_sync.set(True)
    try:
        if case == 'error':
            with pytest.raises(TaskReadError):
                await core.sync('task-1', orgs=None)
            assert await current_counts(factory) == (1, 2, 1, 0, 0)
        else:
            result = await core.sync('task-1', orgs=None)
            assert result.status == {'extended': 'updated', 'recreated': 'recreated', 'missing': 'backed_up'}[case]
    finally:
        automatic_sync.reset(token)


@pytest.mark.asyncio
async def test_skipped_prepare_rejects_later_revision(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    value = snapshot()
    value.task['test_end_ut'] = 100
    reader = AsyncMock()
    reader.read_sendtask.return_value = {'data': value.task, 'metadata': value.metadata}
    core = TaskSyncService(factory, reader)
    token = automatic_sync.set(True)
    try:
        prepared = await core.prepare('task-1', orgs=None)
    finally:
        automatic_sync.reset(token)
    async with factory() as session:
        await session.execute(update(SendTask).values(sync_revision=1))
        await session.commit()
    with pytest.raises(TaskSyncConflict):
        await core.apply(prepared)
    reader.read_task_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_context_is_reset_on_failure():
    @automatic_task_sync
    async def failing():
        assert automatic_sync.get()
        raise RuntimeError('test')
    with pytest.raises(RuntimeError):
        await failing()
    assert not automatic_sync.get()