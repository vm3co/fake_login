import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from backend.repository.database import Base
from backend.repository.models import SendTask, SendLogDetail, SendLogStats, TaskBackup, TaskBackupDetail, CustomerTask
from backend.repository.task_backup_schema import MIGRATION_VERSION, migrate_task_backup_schema


@pytest_asyncio.fixture
async def schema_engine():
    url = os.environ.get("TSB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("TSB_TEST_DATABASE_URL must point to an isolated PostgreSQL instance")
    engine = create_async_engine(url, poolclass=NullPool)
    schema = "tsb_test_" + uuid4().hex
    async with engine.begin() as conn:
        database = (await conn.execute(text("SELECT current_database()"))).scalar_one()
        if database != "tsb_schema_test":
            raise RuntimeError("Schema tests require the dedicated tsb_schema_test database")
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        yield scoped, schema
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def set_path(conn, schema):
    await conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    await conn.execute(text("CREATE SEQUENCE IF NOT EXISTS job_run_queue_sequence"))


def backup_values(generation, **overrides):
    return {
        "source_task_uuid": "task-1", "source_create_ut": 100,
        "source_local_generation_id": generation, "sendtask_id": "Test",
        "owner_gids": ["org-1"], "reason": "remote_missing",
        "task_snapshot": {"sendtask_uuid": "task-1", "sendtask_create_ut": 100},
        **overrides,
    }


@pytest.mark.asyncio
async def test_upgrade_existing_data_is_stable_and_preserves_payload(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(insert(SendTask).values(sendtask_uuid="task-1", sendtask_id="Test", sendtask_owner_gid=["org-1"]))
        await conn.execute(insert(SendTask).values(sendtask_uuid="task-2", sendtask_id="Second", sendtask_owner_gid=[]))
        await conn.execute(insert(SendLogDetail).values(uuid="log-1", sendtask_uuid="task-1", second_input_time=[100, 200], second_input_info=["first", "second"]))
        await conn.execute(insert(SendLogStats).values(sendtask_uuid="task-1", totalplanned=1))
        await conn.execute(text("DROP TABLE task_backup_details, task_backups"))
        await conn.execute(text("ALTER TABLE sendtasks DROP COLUMN local_generation_id, DROP COLUMN sync_revision"))
        await migrate_task_backup_schema(conn)
        first = (await conn.execute(text("SELECT sendtask_uuid, local_generation_id, sync_revision FROM sendtasks ORDER BY sendtask_uuid"))).all()
        assert len({row.local_generation_id for row in first}) == 2
        for row in first:
            UUID(row.local_generation_id)
            assert row.sync_revision == 0
        await conn.execute(text("UPDATE sendtasks SET sync_revision=7 WHERE sendtask_uuid='task-1'"))
        await migrate_task_backup_schema(conn)
        second = (await conn.execute(text("SELECT sendtask_uuid, local_generation_id, sync_revision FROM sendtasks ORDER BY sendtask_uuid"))).all()
        assert [row.local_generation_id for row in first] == [row.local_generation_id for row in second]
        assert second[0].sync_revision == 7
        assert (await conn.execute(select(SendLogDetail.second_input_info))).scalar_one() == ["first", "second"]
        assert (await conn.execute(select(SendLogDetail.second_input_time))).scalar_one() == [100, 200]
        assert (await conn.execute(select(SendLogStats.totalplanned))).scalar_one() == 1
        assert (await conn.execute(text("SELECT count(*) FROM schema_migrations WHERE version=:version"), {"version": MIGRATION_VERSION})).scalar_one() == 1
        assert (await conn.execute(select(TaskBackup.backup_id))).all() == []
        assert (await conn.execute(select(TaskBackupDetail.id))).all() == []
        generation = (await conn.execute(insert(SendTask).values(
            sendtask_uuid="task-3", sendtask_id="After migration", sendtask_owner_gid=[],
        ).returning(SendTask.local_generation_id))).scalar_one()
        UUID(generation)


@pytest.mark.asyncio
async def test_fresh_schema_defaults_and_repeat_migration(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await migrate_task_backup_schema(conn)
        await migrate_task_backup_schema(conn)
        generation, revision = (await conn.execute(insert(SendTask).values(
            sendtask_uuid="task-1", sendtask_id="Test", sendtask_owner_gid=[],
        ).returning(SendTask.local_generation_id, SendTask.sync_revision))).one()
        UUID(generation)
        assert revision == 0
        payload = {"sendtask_uuid": "task-1", "nullable": None, "mail_delivery": {"days": [1, 2]}}
        backup = (await conn.execute(insert(TaskBackup).values(**backup_values(
            generation, task_snapshot=payload, mail_template_snapshot={"template-1": {"title": "Original"}},
        )).returning(TaskBackup.__table__))).mappings().one()
        UUID(backup["backup_id"])
        assert backup["stats_snapshot_at"] is None
        assert backup["stats_snapshot"] is None
        assert backup["snapshot_schema_version"] == 1
        assert backup["latest_remote_status"] == "unchecked"
        assert backup["backed_up_at"].tzinfo is not None
        assert backup["task_snapshot"] == payload
        assert backup["mail_template_snapshot"] == {"template-1": {"title": "Original"}}


@pytest.mark.asyncio
async def test_backup_generations_and_detail_identity_are_independent(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await migrate_task_backup_schema(conn)
        first = (await conn.execute(insert(TaskBackup).values(**backup_values("generation-1")).returning(TaskBackup.backup_id))).scalar_one()
        second = (await conn.execute(insert(TaskBackup).values(**backup_values("generation-2")).returning(TaskBackup.backup_id))).scalar_one()
        for backup_id in (first, second):
            await conn.execute(insert(TaskBackupDetail).values(backup_id=backup_id, uuid="same-log", sendtask_uuid="task-1", second_access_time=[100, 200]))
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(insert(TaskBackup).values(**backup_values("generation-1")))
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(insert(TaskBackupDetail).values(backup_id=first, uuid="same-log", sendtask_uuid="task-1"))
        assert len((await conn.execute(select(TaskBackup.backup_id))).all()) == 2
        assert len((await conn.execute(select(TaskBackupDetail.id))).all()) == 2


@pytest.mark.asyncio
async def test_cascade_only_removes_selected_backup(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await migrate_task_backup_schema(conn)
        await conn.execute(insert(SendTask).values(sendtask_uuid="task-1", sendtask_id="Current", sendtask_owner_gid=["new-org"]))
        await conn.execute(insert(CustomerTask).values(customer_uuid="customer-1", sendtask_uuid="task-1", task_name="Current"))
        await conn.execute(insert(SendLogDetail).values(uuid="same-log", sendtask_uuid="task-1"))
        backups = []
        for generation in ("old-1", "old-2"):
            backup_id = (await conn.execute(insert(TaskBackup).values(**backup_values(generation)).returning(TaskBackup.backup_id))).scalar_one()
            backups.append(backup_id)
            await conn.execute(insert(TaskBackupDetail).values(backup_id=backup_id, uuid="same-log", sendtask_uuid="task-1"))
        await conn.execute(delete(TaskBackup).where(TaskBackup.backup_id == backups[0]))
        assert (await conn.execute(select(TaskBackupDetail.backup_id))).scalar_one() == backups[1]
        assert (await conn.execute(select(SendTask.sendtask_id))).scalar_one() == "Current"
        assert (await conn.execute(select(SendLogDetail.uuid))).scalar_one() == "same-log"
        await conn.execute(delete(SendTask).where(SendTask.sendtask_uuid == "task-1"))
        assert (await conn.execute(select(TaskBackupDetail.backup_id))).scalar_one() == backups[1]
        assert (await conn.execute(select(TaskBackup.owner_gids))).scalar_one() == ["org-1"]
        assert (await conn.execute(select(CustomerTask.customer_uuid))).scalar_one() == "customer-1"


@pytest.mark.asyncio
async def test_failed_migration_rolls_back_columns_backfill_and_marker(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(insert(SendTask).values(sendtask_uuid="task-1", sendtask_id="Original", sendtask_owner_gid=[]))
        await conn.execute(text("DROP TABLE task_backup_details, task_backups"))
        await conn.execute(text("ALTER TABLE sendtasks DROP COLUMN local_generation_id, DROP COLUMN sync_revision"))

    from unittest.mock import patch
    async with engine.begin() as conn:
        await set_path(conn, schema)
        original_run_sync = conn.run_sync
        calls = 0

        async def fail_second_table(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected table creation failure")
            return await original_run_sync(*args, **kwargs)

        with pytest.raises(RuntimeError, match="injected"):
            async with conn.begin_nested():
                with patch.object(type(conn), "run_sync", side_effect=fail_second_table):
                    await migrate_task_backup_schema(conn)
        assert (await conn.execute(text(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema=:schema "
            "AND table_name='sendtasks' AND column_name='local_generation_id'"
        ), {"schema": schema})).scalar_one() == 0
        assert (await conn.execute(select(SendTask.sendtask_id))).scalar_one() == "Original"
        assert (await conn.execute(text("SELECT to_regclass('task_backups')"))).scalar_one() is None
        assert (await conn.execute(text("SELECT to_regclass('schema_migrations')"))).scalar_one() is None
        await migrate_task_backup_schema(conn)
        assert (await conn.execute(select(SendTask.local_generation_id))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"reason": "delete"}, {"latest_remote_status": "unknown"}, {"snapshot_schema_version": 0},
])
async def test_invalid_backup_states_are_rejected(schema_engine, overrides):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        await migrate_task_backup_schema(conn)
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(insert(TaskBackup).values(**backup_values("generation-1", **overrides)))
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(insert(TaskBackupDetail).values(backup_id=str(uuid4()), uuid="orphan", sendtask_uuid="task-1"))


@pytest.mark.asyncio
async def test_partial_existing_columns_only_backfill_null_values(schema_engine):
    engine, schema = schema_engine
    async with engine.begin() as conn:
        await set_path(conn, schema)
        await conn.run_sync(Base.metadata.create_all)
        generation = str(uuid4())
        await conn.execute(insert(SendTask).values(
            sendtask_uuid="task-1", sendtask_id="Known", sendtask_owner_gid=[],
            local_generation_id=generation, sync_revision=12,
        ))
        await conn.execute(text(
            "ALTER TABLE sendtasks ALTER COLUMN local_generation_id DROP NOT NULL, "
            "ALTER COLUMN sync_revision DROP NOT NULL"
        ))
        await conn.execute(insert(SendTask).values(
            sendtask_uuid="task-2", sendtask_id="Partial", sendtask_owner_gid=[],
            local_generation_id=None, sync_revision=None,
        ))
        await migrate_task_backup_schema(conn)
        rows = (await conn.execute(select(
            SendTask.local_generation_id, SendTask.sync_revision,
        ).order_by(SendTask.sendtask_uuid))).all()
        assert rows[0] == (generation, 12)
        UUID(rows[1].local_generation_id)
        assert rows[1].sync_revision == 0


def test_current_and_backup_have_identical_mail_event_fields():
    identity = {"id", "uuid", "sendtask_uuid", "backup_id"}
    current = {column.name: column for column in SendLogDetail.__table__.columns if column.name not in identity}
    backup = {column.name: column for column in TaskBackupDetail.__table__.columns if column.name not in identity}
    assert current.keys() == backup.keys()
    assert "second_input_info" in backup
    for name in current:
        assert str(current[name].type) == str(backup[name].type)
        assert current[name].nullable == backup[name].nullable