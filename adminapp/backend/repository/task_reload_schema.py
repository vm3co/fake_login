from sqlalchemy import Column, Table, Text, String, TIMESTAMP, CheckConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

from backend.repository.database import Base


MIGRATION_VERSION = "20261110_task_reload_operations_v1"

task_reload_operations = Table(
    "task_reload_operations", Base.metadata,
    Column("operation_id", String(36), primary_key=True),
    Column("task_uuid", String(36), primary_key=True),
    Column("actor", Text, nullable=False),
    Column("owner_gids", ARRAY(Text), nullable=False),
    Column("source_generation", String(36), nullable=False),
    Column("result", JSONB, nullable=False),
    Column("committed_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("length(actor) > 0", name="ck_task_reload_operations_actor"),
)


async def migrate_task_reload_schema(conn):
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    ))
    await conn.execute(text("SELECT pg_advisory_xact_lock(61110008)"))
    await conn.run_sync(lambda sync_conn: task_reload_operations.create(sync_conn, checkfirst=True))
    await conn.execute(text(
        "INSERT INTO schema_migrations (version) VALUES (:version) ON CONFLICT DO NOTHING"
    ), {"version": MIGRATION_VERSION})