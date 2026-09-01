import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

# Database Configuration
POSTGRES_USER = os.getenv("POSTGRES_USER", "myuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "mypassword")
POSTGRES_DB = os.getenv("POSTGRES_DB", "mydatabase")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres-db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create Async Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL logging
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

# Create Session Factory
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass

async def get_db():
    """Dependency for getting async session"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    """Initializes the database by creating all tables defined in models."""
    # 延遲 import 避免循環 (models.py 需要本檔的 Base)
    from backend.repository import models  # noqa: F401
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to reset DB
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        migration_version = "20260827_timestamptz_notifications_job_runs"
        applied = await conn.execute(text(
            "SELECT 1 FROM schema_migrations WHERE version = :version"
        ), {"version": migration_version})
        if applied.scalar_one_or_none() is None:
            notification_type = await conn.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'notifications' "
                "AND column_name = 'timestamp'"
            ))
            job_run_types = await conn.execute(text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'job_runs' "
                "AND column_name IN ('started_at', 'finished_at')"
            ))
            notification_type = notification_type.scalar_one_or_none()
            job_run_types = dict(job_run_types.all())

            # Existing values were written as Asia/Taipei wall time despite the DB UTC session.
            if notification_type == "timestamp without time zone":
                await conn.execute(text(
                    "ALTER TABLE notifications "
                    "ALTER COLUMN timestamp DROP DEFAULT, "
                    "ALTER COLUMN timestamp TYPE TIMESTAMPTZ "
                    "USING timestamp AT TIME ZONE 'Asia/Taipei', "
                    "ALTER COLUMN timestamp SET DEFAULT CURRENT_TIMESTAMP"
                ))
            elif notification_type not in {None, "timestamp with time zone"}:
                raise RuntimeError(f"Unexpected notifications.timestamp type: {notification_type}")

            started_type = job_run_types.get("started_at")
            finished_type = job_run_types.get("finished_at")
            if started_type == "timestamp without time zone" and finished_type == "timestamp without time zone":
                await conn.execute(text(
                    "ALTER TABLE job_runs "
                    "ALTER COLUMN started_at DROP DEFAULT, "
                    "ALTER COLUMN started_at TYPE TIMESTAMPTZ "
                    "USING started_at AT TIME ZONE 'Asia/Taipei', "
                    "ALTER COLUMN started_at SET DEFAULT CURRENT_TIMESTAMP, "
                    "ALTER COLUMN finished_at TYPE TIMESTAMPTZ "
                    "USING finished_at AT TIME ZONE 'Asia/Taipei'"
                ))
            elif started_type is not None and (
                started_type != "timestamp with time zone" or finished_type != "timestamp with time zone"
            ):
                raise RuntimeError(
                    f"Unexpected job_runs time types: started_at={started_type}, finished_at={finished_type}"
                )

            await conn.execute(text(
                "INSERT INTO schema_migrations (version) VALUES (:version)"
            ), {"version": migration_version})
        await conn.execute(text(
            "ALTER TABLE job_runs "
            "ADD COLUMN IF NOT EXISTS job_code VARCHAR(64), "
            "ADD COLUMN IF NOT EXISTS display_name TEXT, "
            "ADD COLUMN IF NOT EXISTS request_params JSONB"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_job_runs_job_code ON job_runs(job_code)"
        ))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS job_run_items ("
            "id SERIAL PRIMARY KEY, "
            "job_id VARCHAR(36) NOT NULL REFERENCES job_runs(job_id) ON DELETE CASCADE, "
            "sendtask_uuid VARCHAR(36) NOT NULL, "
            "sendtask_id TEXT NOT NULL, "
            "status VARCHAR(20) NOT NULL DEFAULT 'pending', "
            "reason TEXT, "
            "started_at TIMESTAMPTZ, "
            "finished_at TIMESTAMPTZ"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_job_run_items_job_id ON job_run_items(job_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_job_run_items_sendtask_uuid ON job_run_items(sendtask_uuid)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_job_run_items_active_sendtask "
            "ON job_run_items(sendtask_uuid) "
            "WHERE status IN ('pending', 'running')"
        ))
        await conn.execute(text(
            "UPDATE job_runs SET status = 'failed', "
            "error = COALESCE(error, '服務重新啟動前未完成的舊版背景任務'), "
            "finished_at = CURRENT_TIMESTAMP "
            "WHERE source = 'manual' AND status IN ('pending', 'running')"
        ))
        # 補上既有資料表新增欄位 (idempotent)
        await conn.execute(text(
            "ALTER TABLE trigger_pages "
            "ADD COLUMN IF NOT EXISTS allowed_domain_id INTEGER REFERENCES domains(id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trigger_pages_allowed_domain_id "
            "ON trigger_pages(allowed_domain_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE domains ADD COLUMN IF NOT EXISTS source_company TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE domains ADD COLUMN IF NOT EXISTS notes TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE customer_accts ADD COLUMN IF NOT EXISTS max_task_count INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE sendlog_stats ADD COLUMN IF NOT EXISTS next_plan_time BIGINT"
        ))
        await conn.execute(text(
            "ALTER TABLE accts "
            "ADD COLUMN IF NOT EXISTS acct_locale_code TEXT, "
            "ADD COLUMN IF NOT EXISTS acct_create_ut BIGINT, "
            "ADD COLUMN IF NOT EXISTS acct_update_ut BIGINT, "
            "ADD COLUMN IF NOT EXISTS acct_update_scrt_ut BIGINT, "
            "ADD COLUMN IF NOT EXISTS acct_last_login_ut BIGINT, "
            "ADD COLUMN IF NOT EXISTS acct_last_login_info TEXT, "
            "ADD COLUMN IF NOT EXISTS admin_role BOOLEAN, "
            "ADD COLUMN IF NOT EXISTS agent_role BOOLEAN"
        ))
        # sendtasks: 補上 SE2 get_testcase 完整欄位 (idempotent)
        await conn.execute(text(
            "ALTER TABLE sendtasks "
            "ADD COLUMN IF NOT EXISTS testcase_uuid TEXT, "
            "ADD COLUMN IF NOT EXISTS testcase_id TEXT, "
            "ADD COLUMN IF NOT EXISTS testcase_unit TEXT, "
            "ADD COLUMN IF NOT EXISTS testcase_create_ut BIGINT, "
            "ADD COLUMN IF NOT EXISTS testcase_update_ut BIGINT, "
            "ADD COLUMN IF NOT EXISTS pre_test_person_count INTEGER, "
            "ADD COLUMN IF NOT EXISTS test_person_count INTEGER, "
            "ADD COLUMN IF NOT EXISTS mail_server TEXT[], "
            "ADD COLUMN IF NOT EXISTS mail_speed INTEGER, "
            "ADD COLUMN IF NOT EXISTS mail_logic INTEGER, "
            "ADD COLUMN IF NOT EXISTS mail_logging INTEGER, "
            "ADD COLUMN IF NOT EXISTS mail_template TEXT[], "
            "ADD COLUMN IF NOT EXISTS mail_delivery JSONB, "
            "ADD COLUMN IF NOT EXISTS mail_delivery_d BIGINT[], "
            "ADD COLUMN IF NOT EXISTS testcase_owner_gid TEXT[], "
            "ADD COLUMN IF NOT EXISTS testcase_public BOOLEAN, "
            "ADD COLUMN IF NOT EXISTS alert_content TEXT, "
            "ADD COLUMN IF NOT EXISTS redirect_url TEXT, "
            "ADD COLUMN IF NOT EXISTS clicklink_action INTEGER, "
            "ADD COLUMN IF NOT EXISTS adv_mail_delivery BOOLEAN, "
            "ADD COLUMN IF NOT EXISTS adv_mail_delivery_val JSONB"
        ))

