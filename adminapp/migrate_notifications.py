import asyncio
import sys
import os

# Add the parent directory to sys.path to allow imports from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.repository.db_controller import ApplianceDB
from backend.services.log_manager import Logger

logger = Logger().get_logger()

async def migrate():
    db = ApplianceDB()
    await db.db_init()
    
    try:
        logger.info("Attempting to add 'details' column to 'notifications' table...")
        await db.execute_query('ALTER TABLE "notifications" ADD COLUMN IF NOT EXISTS "details" TEXT;')
        logger.info("Migration successful: 'details' column added.")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        await db.db_close()

if __name__ == "__main__":
    asyncio.run(migrate())
