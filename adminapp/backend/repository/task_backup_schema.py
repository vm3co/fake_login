from sqlalchemy import text


MIGRATION_VERSION = "20261105_task_backup_versions_v1"


async def migrate_task_backup_schema(conn):
    from backend.repository.models import TaskBackup, TaskBackupDetail

    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, "
        "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    ))
    await conn.execute(text("SELECT pg_advisory_xact_lock(61105002)"))
    applied = await conn.execute(text(
        "SELECT 1 FROM schema_migrations WHERE version = :version"
    ), {"version": MIGRATION_VERSION})
    if applied.scalar_one_or_none() is not None:
        return

    await conn.execute(text(
        "ALTER TABLE sendtasks "
        "ADD COLUMN IF NOT EXISTS local_generation_id VARCHAR(36), "
        "ADD COLUMN IF NOT EXISTS sync_revision BIGINT"
    ))
    await conn.execute(text(
        "UPDATE sendtasks SET local_generation_id = gen_random_uuid()::text "
        "WHERE local_generation_id IS NULL"
    ))
    await conn.execute(text(
        "UPDATE sendtasks SET sync_revision = 0 WHERE sync_revision IS NULL"
    ))
    await conn.execute(text(
        "ALTER TABLE sendtasks "
        "ALTER COLUMN local_generation_id SET DEFAULT gen_random_uuid()::text, "
        "ALTER COLUMN local_generation_id SET NOT NULL, "
        "ALTER COLUMN sync_revision SET DEFAULT 0, "
        "ALTER COLUMN sync_revision SET NOT NULL"
    ))
    await conn.run_sync(lambda sync_conn: TaskBackup.__table__.create(sync_conn, checkfirst=True))
    await conn.run_sync(lambda sync_conn: TaskBackupDetail.__table__.create(sync_conn, checkfirst=True))
    await conn.execute(text(
        "INSERT INTO schema_migrations (version) VALUES (:version)"
    ), {"version": MIGRATION_VERSION})