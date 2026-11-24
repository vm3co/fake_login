import asyncio
import json
import logging

from sqlalchemy import select

from backend.repository.models import SendTask, SendLogDetail
from backend.services.task_sync import TaskSyncConflict


logger = logging.getLogger(__name__)


class TaskDetailsCache:
    def __init__(self, session_factory, redis_factory):
        self.session_factory = session_factory
        self.redis_factory = redis_factory

    async def version(self, task_uuid):
        async with self.session_factory() as session:
            row = (await session.execute(select(
                SendTask.local_generation_id, SendTask.sync_revision,
            ).where(SendTask.sendtask_uuid == task_uuid))).one_or_none()
        return tuple(row) if row is not None else None

    async def snapshot(self, task_uuid):
        async with self.session_factory() as session:
            rows = (await session.execute(select(
                SendTask.local_generation_id.label("_generation"),
                SendTask.sync_revision.label("_revision"), SendTask.is_archived.label("_archived"),
                *SendLogDetail.__table__.columns,
            ).outerjoin(SendLogDetail, SendLogDetail.sendtask_uuid == SendTask.sendtask_uuid).where(
                SendTask.sendtask_uuid == task_uuid,
            ).order_by(SendLogDetail.id))).mappings().all()
        if not rows:
            return None, False, []
        version = (rows[0]["_generation"], rows[0]["_revision"])
        data = [{column.name: row[column.name] for column in SendLogDetail.__table__.columns}
                for row in rows if row["uuid"] is not None]
        return version, rows[0]["_archived"] is True, data

    async def redis_call(self, method, *args, **kwargs):
        async def call():
            client = await self.redis_factory()
            return await getattr(client, method)(*args, **kwargs)

        try:
            return await asyncio.wait_for(call(), timeout=0.5)
        except Exception as exc:
            logger.warning("Task details cache %s failed: %s", method, exc)
            return None

    @staticmethod
    def decode(value, task_uuid, version):
        try:
            envelope = json.loads(value)
        except (ValueError, TypeError):
            return None
        if (
            not isinstance(envelope, dict) or type(envelope.get("schema_version")) is not int
            or envelope["schema_version"] != 1 or envelope.get("task_uuid") != task_uuid
            or not isinstance(envelope.get("generation"), str) or type(envelope.get("revision")) is not int
            or (envelope.get("generation"), envelope.get("revision")) != version
            or not isinstance(envelope.get("data"), list)
        ):
            return None
        data = envelope["data"]
        if any(not isinstance(row, dict) or row.get("sendtask_uuid") != task_uuid or "id" not in row for row in data):
            return None
        return data

    async def get(self, task_uuid, *, need_id=True, use_cache=True):
        key = f"task:{task_uuid}:details"
        for attempt in range(3):
            version = await self.version(task_uuid)
            if version is None:
                return []
            if not isinstance(version[0], str) or not version[0] or type(version[1]) is not int:
                raise TaskSyncConflict("Current task version is unavailable")
            if use_cache:
                cached = self.decode(await self.redis_call("get", key), task_uuid, version)
                if cached is not None and await self.version(task_uuid) == version:
                    return self.project(cached, need_id)
            captured, archived, data = await self.snapshot(task_uuid)
            if captured is None:
                return []
            if not isinstance(captured[0], str) or not captured[0] or type(captured[1]) is not int:
                raise TaskSyncConflict("Current task version is unavailable")
            if captured != await self.version(task_uuid):
                continue
            envelope = {
                "schema_version": 1, "task_uuid": task_uuid,
                "generation": captured[0], "revision": captured[1], "data": data,
            }
            await self.redis_call("set", key, json.dumps(envelope, default=str), ex=3600 if archived else 86400)
            if captured == await self.version(task_uuid):
                return self.project(data, need_id)
        raise TaskSyncConflict("Task changed repeatedly while reading details")

    @staticmethod
    def project(data, need_id):
        return [{key: value for key, value in row.items() if need_id or key != "id"} for row in data]