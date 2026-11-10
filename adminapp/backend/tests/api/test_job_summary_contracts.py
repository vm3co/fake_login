from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_today_task_job_distinguishes_added_and_existing(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app
    from backend.services.db_user import DBUser
    from backend.services.task_sync_core import TaskSyncResult

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "username": "user-a",
        "orgs": ["org-a"],
    }
    today_tasks = [
        {"sendtask_uuid": "new", "sendtask_id": "新增任務", "sendtask_owner_gid": ["org-a"]},
        {"sendtask_uuid": "existing", "sendtask_id": "既有任務", "sendtask_owner_gid": ["org-a"]},
    ]
    core = AsyncMock(session_factory=None)
    core.sync.side_effect = [
        TaskSyncResult("added", "new", "new-generation", 0, None, True, ("new",), False),
        TaskSyncResult("updated", "existing", "existing-generation", 1, None, True, ("existing",), False),
    ]
    service = DBUser(task_sync=core)

    captured = {}

    async def start_job(_username, _name, task_func, **_kwargs):
        captured["result"] = await task_func()
        return {"job_id": "job-today", "accepted": [], "excluded": []}

    try:
           with patch("backend.api.job_api.db_user", new=service), \
               patch.object(service, "refresh_today_create_task", new=AsyncMock(return_value=today_tasks)), \
               patch("backend.api.job_api.db_controller.upsert", new=AsyncMock(side_effect=AssertionError("No header upsert"))), \
             patch("backend.api.job_api.job_manager.start_job", new=start_job):
            response = await async_client.post("/api/jobs/start", json={
                "job_type": "refresh_today_create_task",
                "params": {},
            })
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert captured["result"]["added_tasks"] == [
        {"sendtask_uuid": "new", "sendtask_id": "新增任務"}
    ]
    assert captured["result"]["updated_tasks"] == [
        {"sendtask_uuid": "existing", "sendtask_id": "既有任務"}
    ]
