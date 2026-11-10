from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.api.data_api import filter_tasks_by_scope, get_sendtask_scope, require_sendtask_access


class _Task:
    __table__ = SimpleNamespace(columns=(
        SimpleNamespace(name="sendtask_uuid"),
        SimpleNamespace(name="sendtask_owner_gid"),
    ))

    def __init__(self, uuid, orgs):
        self.sendtask_uuid = uuid
        self.sendtask_owner_gid = orgs


def _task(uuid, orgs):
    return _Task(uuid, orgs)


def test_regular_user_scope_uses_trusted_principal_orgs():
    scope = get_sendtask_scope({
        "user_type": "user",
        "admin_role": False,
        "orgs": ["org-1"],
    })

    visible = filter_tasks_by_scope(
        [_task("task-1", ["org-1"]), _task("task-2", ["org-2"])],
        scope,
    )

    assert [task.sendtask_uuid for task in visible] == ["task-1"]


def test_admin_role_has_unrestricted_sendtask_scope():
    assert get_sendtask_scope({"user_type": "user", "admin_role": True, "orgs": []}) is None


def test_platform_admin_has_no_sendtask_scope():
    with pytest.raises(Exception) as error:
        get_sendtask_scope({"user_type": "platform_admin", "admin_role": False, "orgs": []})

    assert getattr(error.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_get_sendtasks_ignores_forged_request_orgs(async_client, monkeypatch):
    from backend.main import app
    from backend.api.user_api import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "orgs": ["org-1"],
        "username": "user@example.com",
    }
    permitted = _task("task-1", ["org-1"])
    forbidden = _task("task-2", ["org-2"])

    try:
        with patch("backend.api.data_api.db_controller.get", new=AsyncMock(return_value=[permitted, forbidden])):
            response = await async_client.post("/api/get_sendtasks", json={"orgs": ["admin"]})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert [task["sendtask_uuid"] for task in response.json()["data"]] == ["task-1"]


@pytest.mark.asyncio
async def test_mtmpl_filter_admin_role_sees_all_tasks(async_client):
    from backend.main import app
    from backend.api.user_api import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": True,
        "orgs": [],
        "username": "admin-role@example.com",
    }
    first = SimpleNamespace(sendtask_id="Task A", mail_template=["m-1"], sendtask_owner_gid=["org-1"])
    second = SimpleNamespace(sendtask_id="Task B", mail_template=["m-2"], sendtask_owner_gid=["org-2"])

    try:
        with patch("backend.api.data_api.db_controller.get", new=AsyncMock(return_value=[first, second])):
            response = await async_client.get("/api/get_mtmpl_task_filters")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert [item["sendtask_id"] for item in response.json()["data"]] == ["Task A", "Task B"]


@pytest.mark.asyncio
async def test_sendlog_detail_rejects_task_outside_principal_scope(async_client):
    from backend.main import app
    from backend.api.user_api import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "orgs": ["org-1"],
        "username": "user@example.com",
    }
    forbidden = _task("task-2", ["org-2"])

    try:
        with patch("backend.api.data_api.db_controller.get_one", new=AsyncMock(return_value=forbidden)):
            response = await async_client.post("/api/get_sendlog_detail", json={
                "sendtask_uuid": "task-2",
                "acctControl": [True, True, True, True, True],
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "無權存取指定任務"


@pytest.mark.asyncio
async def test_admin_role_can_access_any_sendtask_detail():
    permitted = _task("task-2", ["org-2"])
    current_user = {
        "user_type": "user",
        "admin_role": True,
        "orgs": [],
        "username": "admin-role@example.com",
    }

    with patch("backend.api.data_api.db_controller.get_one", new=AsyncMock(return_value=permitted)):
        result = await require_sendtask_access("task-2", current_user)

    assert result is permitted