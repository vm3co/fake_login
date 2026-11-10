from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


RUNTIME_VALUES = {
    "scheduler_refresh_token_enabled": True,
    "scheduler_refresh_today_create_task_enabled": False,
    "scheduler_refresh_notyet_today_tasks_enabled": True,
    "scheduler_nightly_sync_enabled": True,
    "scheduler_archiving_enabled": False,
    "startup_cache_warming_enabled": True,
}
SCHEDULE_VALUES = {
    "scheduler_refresh_token_minutes": 10,
    "scheduler_refresh_today_create_task_minutes": 60,
    "scheduler_refresh_notyet_today_tasks_minutes": 30,
    "scheduler_nightly_sync_time": "01:00",
    "scheduler_archiving_time": "02:00",
}


@pytest.mark.asyncio
async def test_runtime_config_rejects_non_platform_admin(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "username": "user-a",
    }
    try:
        response = await async_client.get("/api/system/runtime-config")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_updates_and_applies_runtime_config(async_client, monkeypatch):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "platform_admin",
        "username": "platform@example.com",
    }
    apply_runtime_config = AsyncMock(return_value=RUNTIME_VALUES)
    app.state.apply_runtime_config = apply_runtime_config
    monkeypatch.setattr("backend.api.user_api.ADMIN_CONTROL_PASSWORD", "control-secret")

    try:
        with patch("backend.api.user_api.db_controller.get_one", new=AsyncMock(return_value=None)), \
             patch("backend.api.user_api.db_controller.create", new=AsyncMock()):
            response = await async_client.post("/api/system/runtime-config", json={
                "control_password": "control-secret",
                **RUNTIME_VALUES,
                **SCHEDULE_VALUES,
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["configured"] == RUNTIME_VALUES
    assert response.json()["schedule"] == SCHEDULE_VALUES
    apply_runtime_config.assert_awaited_once_with(RUNTIME_VALUES, SCHEDULE_VALUES)


@pytest.mark.asyncio
async def test_runtime_config_rejects_invalid_schedule_values(async_client, monkeypatch):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "platform_admin",
        "username": "platform@example.com",
    }
    app.state.apply_runtime_config = AsyncMock()
    monkeypatch.setattr("backend.api.user_api.ADMIN_CONTROL_PASSWORD", "control-secret")

    try:
        response = await async_client.post("/api/system/runtime-config", json={
            "control_password": "control-secret",
            **RUNTIME_VALUES,
            **SCHEDULE_VALUES,
            "scheduler_refresh_token_minutes": 4,
        })
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422