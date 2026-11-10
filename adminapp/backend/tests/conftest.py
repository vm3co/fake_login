import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import os
from unittest.mock import AsyncMock

# 強制設定測試環境變數
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "password123"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["APP_BASE_DIR"] = "/tmp/test_app_base"

# Avoid import errors by mocking if necessary, but better to import after env set
from backend.main import app, db_user

# Global mocks for db_user to prevent DB access during import/setup
db_user.table_initialize = AsyncMock()
db_user.refresh_sendlog_stats = AsyncMock()
db_user.user_exists = AsyncMock(return_value=False)
db_user.get_se2_sendtasks = AsyncMock(return_value=[])
db_user.refresh_today_create_task = AsyncMock(return_value=[])

@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
