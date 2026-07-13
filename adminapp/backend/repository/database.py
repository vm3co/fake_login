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

