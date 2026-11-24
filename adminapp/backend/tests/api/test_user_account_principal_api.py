from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.core.security import create_access_token, hash_password
from backend.main import db_user


def _registered_account(*, is_active=True, admin_role=False, acct_id="renamed@example.com"):
    user = SimpleNamespace(
        acct_uuid="acct-1",
        username="old@example.com",
        password_hash=hash_password("secret"),
    )
    acct = SimpleNamespace(
        acct_uuid="acct-1",
        acct_id=acct_id,
        acct_full_name="Renamed User",
        orgs=["org-1"],
        is_active=is_active,
        admin_role=admin_role,
    )
    return user, acct


@pytest.mark.asyncio
async def test_login_reads_profile_from_acct(async_client: AsyncClient):
    registered_account = _registered_account()

    with patch.object(
        db_user,
        "get_registered_account",
        new=AsyncMock(return_value=registered_account),
    ), patch.object(db_user, "add_login_log", new=AsyncMock()), patch(
        "backend.api.user_api.db_controller.get_one",
        new=AsyncMock(return_value=None),
    ):
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "RENAMED@example.com", "password": "secret"},
        )

    assert response.status_code == 200
    assert response.json()["user"] == {
        "acct_uuid": "acct-1",
        "name": "renamed@example.com",
        "orgs": ["org-1"],
        "user_type": "user",
        "admin_role": False,
        "full_name": "Renamed User",
    }


@pytest.mark.asyncio
async def test_profile_uses_uuid_after_acct_id_rename(async_client: AsyncClient):
    token = create_access_token({
        "acct_uuid": "acct-1",
        "username": "old@example.com",
        "user_type": "user",
    })

    with patch.object(
        db_user,
        "get_registered_account",
        new=AsyncMock(return_value=_registered_account()),
    ) as get_registered_account:
        response = await async_client.get(
            "/api/auth/profile",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["name"] == "renamed@example.com"
    get_registered_account.assert_awaited_once_with(acct_uuid="acct-1")


@pytest.mark.asyncio
async def test_profile_rejects_inactive_acct(async_client: AsyncClient):
    token = create_access_token({
        "acct_uuid": "acct-1",
        "username": "old@example.com",
        "user_type": "user",
    })

    with patch.object(
        db_user,
        "get_registered_account",
        new=AsyncMock(return_value=_registered_account(is_active=False)),
    ):
        response = await async_client.get(
            "/api/auth/profile",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "帳號已停用"