import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, update, select, func
from redis.asyncio import Redis

from backend.repository.models import SendTask, SendLogDetail, TaskBackup, TaskBackupDetail
from backend.services.task_details_cache import TaskDetailsCache
from backend.services.task_sync_core import TaskSyncService
from backend.services.task_sync import TaskSyncConflict
from backend.tests.repository.test_task_backup_schema import schema_engine
from backend.tests.services.test_task_backup_transfer import setup_transfer
from backend.tests.services.test_task_sync_core import snapshot
from backend.services.se2_task_reader import TaskNotFound


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, **kwargs):
        self.values[key] = value

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


@pytest.mark.asyncio
async def test_multiversion_pipeline_with_real_redis_and_independent_history(schema_engine):
    url = os.environ.get('TSB_TEST_REDIS_URL')
    if not url:
        pytest.skip('TSB_TEST_REDIS_URL must target dedicated tsb016-redis')
    from urllib.parse import urlparse
    target = urlparse(url)
    if target.hostname != 'tsb016-redis' or target.path != '/15':
        raise RuntimeError('Pipeline test requires isolated tsb016-redis database 15')
    redis = Redis.from_url(url, decode_responses=True)
    factory, _, _ = await setup_transfer(schema_engine)
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    key = 'task:task-1:details'
    await redis.delete(key)
    try:
        assert await redis.ping()
        original = await cache.get('task-1')
        assert len(original) == 2
        stale = await redis.get(key)
        reader = AsyncMock(read_task_snapshot=AsyncMock(side_effect=TaskNotFound('missing')))
        core = TaskSyncService(factory, reader)
        with patch('backend.services.redis_client.RedisClient.get_client', AsyncMock(return_value=redis)):
            removed = await core.sync('task-1', orgs=['org-1'])
            assert removed.status == 'backed_up'
            await redis.set(key, stale)
            assert await cache.get('task-1') == []
            reader.read_task_snapshot.side_effect = None
            reader.read_task_snapshot.return_value = snapshot(200, 5)
            imported = await core.sync('task-1', orgs=['org-1'])
            assert imported.status == 'added'
            assert len(await cache.get('task-1')) == 5
            reader.read_task_snapshot.return_value = snapshot(300, 3)
            recreated = await core.sync('task-1', orgs=['org-1'])
            assert recreated.status == 'recreated'
        await redis.set(key, stale)
        latest = await cache.get('task-1')
        assert len(latest) == 3
        assert all(row['second_input_time'] is None for row in latest)
        async with factory() as session:
            backups = (await session.scalars(select(TaskBackup).order_by(TaskBackup.source_create_ut))).all()
            assert [backup.source_create_ut for backup in backups] == [100, 200]
            assert len({backup.source_local_generation_id for backup in backups} | {recreated.generation}) == 3
            first_rows = (await session.scalars(select(TaskBackupDetail).where(TaskBackupDetail.backup_id == removed.backup_id))).all()
            assert len(first_rows) == 2 and all(row.second_input_time == [70, 80] for row in first_rows)
            second_rows = (await session.scalars(select(TaskBackupDetail).where(TaskBackupDetail.backup_id == recreated.backup_id))).all()
            assert len(second_rows) == 5
            assert {row.uuid for row in second_rows} >= {row['uuid'] for row in latest}
            await session.execute(delete(TaskBackup).where(TaskBackup.backup_id == removed.backup_id))
            await session.commit()
            assert await session.scalar(select(func.count()).select_from(TaskBackup)) == 1
            assert await session.scalar(select(func.count()).select_from(TaskBackupDetail)) == 5
            assert await session.scalar(select(func.count()).select_from(SendLogDetail)) == 3
        assert len(await cache.get('task-1')) == 3
    finally:
        await redis.delete(key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_old_cache_is_miss_and_need_id_is_projected_per_request(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    redis = MemoryRedis()
    redis.values["task:task-1:details"] = json.dumps([{"uuid": "old-cache"}])
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    first = await cache.get("task-1", need_id=False)
    assert len(first) == 2 and all("id" not in row for row in first)
    second = await cache.get("task-1", need_id=True)
    assert len(second) == 2 and all("id" in row for row in second)
    envelope = json.loads(redis.values["task:task-1:details"])
    assert envelope["schema_version"] == 1 and envelope["generation"]
    assert envelope["revision"] == 0


@pytest.mark.asyncio
async def test_stale_cache_is_rejected_even_when_invalidation_fails(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    redis = MemoryRedis()
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    await cache.get("task-1")
    stale = redis.values["task:task-1:details"]
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=snapshot(200, 5))))
    with patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(side_effect=RuntimeError("redis down"))):
        result = await core.sync("task-1", orgs=None)
    assert result.committed and result.warnings[0]["stage"] == "cache_invalidation"
    assert redis.values["task:task-1:details"] == stale
    assert len(await cache.get("task-1")) == 5


@pytest.mark.asyncio
async def test_old_reader_late_cache_write_keeps_old_version_and_retries(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    redis = MemoryRedis()
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    core = TaskSyncService(factory, AsyncMock(read_task_snapshot=AsyncMock(return_value=snapshot(200, 5))))
    original_set = redis.set
    envelopes = []

    async def delayed_set(key, value, **kwargs):
        envelopes.append(json.loads(value))
        if len(envelopes) == 1:
            with patch("backend.services.redis_client.RedisClient.get_client", AsyncMock(return_value=redis)):
                await core.sync("task-1", orgs=None)
        await original_set(key, value, **kwargs)

    redis.set = delayed_set
    result = await cache.get("task-1")
    assert len(result) == 5 and len(envelopes) == 2
    assert len(envelopes[0]["data"]) == 2 and len(envelopes[1]["data"]) == 5
    assert envelopes[0]["generation"] != envelopes[1]["generation"]


@pytest.mark.asyncio
async def test_missing_current_never_returns_cache_or_backup(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    redis = MemoryRedis()
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    await cache.get("task-1")
    async with engine.begin() as conn:
        await conn.execute(delete(SendTask))
    assert await cache.get("task-1") == []


@pytest.mark.asyncio
async def test_same_generation_revision_mismatch_and_redis_outage_read_database(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    redis = MemoryRedis()
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    await cache.get("task-1")
    original = json.loads(redis.values["task:task-1:details"])
    async with engine.begin() as conn:
        await conn.execute(update(SendTask).values(sync_revision=1))
    assert len(await cache.get("task-1")) == 2
    current = json.loads(redis.values["task:task-1:details"])
    assert current["generation"] == original["generation"] and current["revision"] == 1
    failing = TaskDetailsCache(factory, AsyncMock(side_effect=RuntimeError("redis down")))
    assert len(await failing.get("task-1")) == 2


@pytest.mark.asyncio
async def test_cache_requires_database_version_and_no_cache_option_skips_get(schema_engine):
    factory, _, _ = await setup_transfer(schema_engine)
    redis = MemoryRedis()
    redis.get = AsyncMock(side_effect=AssertionError("Cache bypass must not read"))
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    assert len(await cache.get("task-1", use_cache=False)) == 2
    redis.get.assert_not_awaited()
    with patch.object(cache, "version", AsyncMock(side_effect=RuntimeError("database unavailable"))):
        with pytest.raises(RuntimeError, match="database unavailable"):
            await cache.get("task-1")


@pytest.mark.parametrize("raw", [
    "bad-json", "[]", "{}",
    json.dumps({"schema_version": 1, "task_uuid": "task-1", "generation": "gen", "revision": True, "data": []}),
    json.dumps({"schema_version": 1, "task_uuid": "task-1", "generation": "gen", "revision": 1, "data": [{"uuid": "wrong-task", "id": 1, "sendtask_uuid": "other"}]}),
])
def test_invalid_or_legacy_cache_is_never_a_hit(raw):
    assert TaskDetailsCache.decode(raw, "task-1", ("gen", 1)) is None


@pytest.mark.asyncio
async def test_empty_details_are_cached_and_archived_ttl_is_preserved(schema_engine):
    from backend.repository.models import SendLogDetail

    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        await conn.execute(delete(SendLogDetail))
        await conn.execute(update(SendTask).values(is_archived=True))
    redis = MemoryRedis()
    redis.set = AsyncMock(wraps=redis.set)
    cache = TaskDetailsCache(factory, AsyncMock(return_value=redis))
    assert await cache.get("task-1") == []
    assert redis.set.await_args.kwargs["ex"] == 3600
    with patch.object(cache, "snapshot", AsyncMock(side_effect=AssertionError("Empty cache should hit"))):
        assert await cache.get("task-1") == []


@pytest.mark.asyncio
async def test_repeated_version_changes_fail_instead_of_returning_stale_data():
    cache = TaskDetailsCache(None, AsyncMock(side_effect=RuntimeError("unused")))
    with patch.object(cache, "version", AsyncMock(side_effect=[("gen", 0), ("gen", 1)] * 3)), \
         patch.object(cache, "snapshot", AsyncMock(return_value=(("gen", 0), False, []))):
        with pytest.raises(TaskSyncConflict):
            await cache.get("task-1", use_cache=False)