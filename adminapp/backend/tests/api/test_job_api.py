from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def make_job(job_id, owner):
    return SimpleNamespace(
        job_id=job_id,
        source="manual",
        job_code="check_sendtasks",
        job_type="更新任務列表",
        display_name="更新任務列表",
        owner_username=owner,
        status="completed",
        execution_class="manual_shared",
        queue_sequence=1,
        cancel_requested_at=None,
        message="完成",
        result={"updated": 1},
        error=None,
        started_at=datetime(2026, 8, 27, 1, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 27, 1, 1, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_regular_user_job_query_is_scoped(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "username": "user-a",
    }
    execute_scalars = AsyncMock(side_effect=[[], [make_job("job-a", "user-a")]])
    try:
           with patch("backend.api.job_api.db_controller.execute_scalars", execute_scalars), \
               patch("backend.api.job_api.db_controller.get", new=AsyncMock(return_value=[])):
            response = await async_client.get("/api/jobs?source=manual")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()[0]["owner_username"] == "user-a"
    assert response.json()[0]["start_time"].endswith("Z")
    statements = [str(call.args[0]) for call in execute_scalars.await_args_list]
    assert all("job_runs.owner_username" in statement for statement in statements)


@pytest.mark.asyncio
async def test_admin_job_query_can_see_all_owners(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": True,
        "username": "admin",
    }
    execute_scalars = AsyncMock(side_effect=[[], [make_job("job-b", "user-b")]])
    try:
           with patch("backend.api.job_api.db_controller.execute_scalars", execute_scalars), \
               patch("backend.api.job_api.db_controller.get", new=AsyncMock(return_value=[])):
            response = await async_client.get("/api/jobs?source=manual")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()[0]["owner_username"] == "user-b"
    statements = [str(call.args[0]).split("WHERE", 1)[1] for call in execute_scalars.await_args_list]
    assert all("job_runs.owner_username" not in where_clause for where_clause in statements)


@pytest.mark.asyncio
async def test_unknown_job_source_is_rejected(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "username": "user-a",
    }
    try:
        response = await async_client.get("/api/jobs?source=unknown")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_scheduler_query_only_includes_failed_token_jobs(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "username": "user-a",
    }
    execute_scalars = AsyncMock(side_effect=[[], []])
    try:
           with patch("backend.api.job_api.db_controller.execute_scalars", execute_scalars), \
               patch("backend.api.job_api.db_controller.get", new=AsyncMock(return_value=[])):
            response = await async_client.get("/api/jobs?source=scheduler")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    statements = [str(call.args[0]) for call in execute_scalars.await_args_list]
    assert all("job_runs.job_type" in statement for statement in statements)
    assert all("job_runs.status =" in statement for statement in statements)


@pytest.mark.asyncio
async def test_partial_job_is_returned_as_history(async_client):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user",
        "admin_role": False,
        "username": "user-a",
    }
    partial_job = make_job("job-partial", "user-a")
    partial_job.status = "partial"
    execute_scalars = AsyncMock(side_effect=[[], [partial_job]])
    try:
        with patch("backend.api.job_api.db_controller.execute_scalars", execute_scalars):
            response = await async_client.get("/api/jobs?source=manual")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()[0]["status"] == "partial"
    history_statement = str(execute_scalars.await_args_list[1].args[0])
    assert "NOT IN" in history_statement