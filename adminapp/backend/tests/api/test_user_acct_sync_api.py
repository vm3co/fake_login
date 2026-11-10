import pytest
from httpx import AsyncClient
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.core.security import create_access_token
from backend.main import db_user


@pytest.mark.asyncio
async def test_sync_accts_upserts_complete_account_payload(async_client: AsyncClient):
    token = create_access_token({
        "acct_uuid": "platform_admin",
        "username": "platform@acercsi.com",
        "user_type": "platform_admin",
    })
    accounts = [{
        "acct_uuid": "a85243aa17e84f0989a289a3ee2c2c02",
        "acct_id": "mike.xu@acercsi.com",
        "acct_full_name": "mike.xu",
        "acct_email": "mike.xu@acercsi.com",
        "acct_locale_code": "zh-TW",
        "acct_create_ut": 1758685340,
        "admin_role": True,
        "agent_role": False,
        "is_active": True,
    }]

    with patch.object(db_user, "get_se2_accts", new=AsyncMock(return_value=accounts)), patch(
        "backend.api.user_api.db_controller.upsert", new=AsyncMock(return_value=1)
    ) as upsert:
        response = await async_client.post(
            "/api/users/sync-accts",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "同步完成。總共處理 1 筆帳號。"
    upsert.assert_awaited_once()
    assert upsert.await_args.args[1] == accounts
    assert upsert.await_args.kwargs["index_elements"] == ["acct_uuid"]


@pytest.mark.asyncio
async def test_sync_accts_rejects_non_platform_admin(async_client: AsyncClient):
    token = create_access_token({
        "acct_uuid": "user-1",
        "username": "user@example.com",
        "user_type": "user",
    })

    account = SimpleNamespace(acct_id="user@example.com", is_active=True)
    with patch(
        "backend.api.user_api.db_controller.execute_scalars",
        new=AsyncMock(return_value=[account]),
    ):
        response = await async_client.post(
            "/api/users/sync-accts",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403