from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update

from backend.repository.models import SendTask
from backend.services.task_sync_core import TaskSyncService
from backend.tests.repository.test_task_backup_schema import schema_engine
from backend.tests.services.test_task_backup_transfer import setup_transfer, current_counts
from backend.tests.services.test_task_sync_core import snapshot
from backend.tests.services.test_task_archive_policy import NOW, CUTOFF


@pytest.mark.asyncio
@pytest.mark.parametrize("old_archived,end,transition", [
    (False, CUTOFF - 1, "archived"), (True, NOW + 86400, "unarchived"),
    (False, CUTOFF, None), (False, None, None),
])
async def test_archive_policy_is_committed_with_full_sync(schema_engine, old_archived, end, transition):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(is_archived=old_archived))
    value = snapshot()
    value.task["test_end_ut"] = end
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=value)))
    result = await core.sync("task-1", orgs=None, archive_at=NOW)
    assert result.archive_transition == transition
    async with factory() as session:
        assert await session.scalar(select(SendTask.is_archived)) is (end is not None and end < CUTOFF)


@pytest.mark.asyncio
async def test_stat_failure_rolls_back_unarchive(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(is_archived=True))
    value = snapshot()
    value.task["test_end_ut"] = NOW + 86400

    def fail(records):
        raise RuntimeError("statistics failed")

    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=value)), stats_calculator=fail)
    with pytest.raises(RuntimeError):
        await core.sync("task-1", orgs=None, archive_at=NOW)
    assert await current_counts(factory) == (1, 2, 1, 0, 0)
    async with factory() as session:
        assert await session.scalar(select(SendTask.is_archived)) is True


@pytest.mark.asyncio
async def test_omitted_end_time_uses_persisted_value(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(test_end_ut=CUTOFF - 1, is_archived=False))
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=snapshot())))
    result = await core.sync("task-1", orgs=None, archive_at=NOW)
    assert result.archive_transition == "archived"
    async with factory() as session:
        assert await session.scalar(select(SendTask.is_archived)) is True