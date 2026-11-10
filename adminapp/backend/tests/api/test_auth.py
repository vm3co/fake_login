import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, AsyncMock, patch
from backend.main import db_user

@pytest.mark.asyncio
async def test_admin_login_success(async_client: AsyncClient):
    """
    測試管理員登入成功
    """
    payload = {
        "username": "admin@example.com",
        "password": "password123"
    }
    response = await async_client.post("/api/auth/login", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "accessToken" in data
    assert data["user"]["user_type"] == "admin"
    assert data["user"]["admin_role"] is True
    assert data["user"]["orgs"] == []

@pytest.mark.asyncio
async def test_admin_login_failed(async_client: AsyncClient):
    """
    測試管理員登入失敗 (密碼錯誤)
    """
    payload = {
        "username": "admin@example.com",
        "password": "wrongpassword"
    }
    
    with patch("backend.api.user_api.db_controller") as mock_db_controller, patch.object(
        db_user, "get_registered_account", new=AsyncMock(return_value=None)
    ):
        mock_db_controller.get_one = AsyncMock(return_value=None)
        mock_db_controller.execute_scalars = AsyncMock(return_value=[])
        response = await async_client.post("/api/auth/login", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "帳號或密碼錯誤"
