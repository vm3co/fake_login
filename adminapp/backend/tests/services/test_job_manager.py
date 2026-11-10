from unittest.mock import AsyncMock, patch

import pytest

from backend.services.job_manager import JobManager


@pytest.mark.asyncio
async def test_job_manager_persists_partial_result():
    manager = JobManager()
    manager.jobs = {}
    create = AsyncMock()
    update = AsyncMock()

    async def task_func(*, accepted_items, job_id):
        return {
            "job_status": "partial",
            "successful_tasks": [{"sendtask_id": "Task A"}],
            "failed_tasks": [{"sendtask_id": "Task B", "reason": "error"}],
        }

    with patch("backend.services.job_manager.db_controller.create", create), \
         patch("backend.services.job_manager.db_controller.update", update):
        admission = await manager.start_job(
            "user-a",
            "更新任務統計",
            task_func,
            items=[{"sendtask_uuid": "task-a", "sendtask_id": "Task A"}],
        )
        handler = __import__("backend.services.job_queue", fromlist=["job_queue"]).job_queue.job_handlers[
            admission["job_id"]
        ]
        await handler(admission["job_id"])

    job = manager.get_current_job("user-a")
    assert job["status"] == "partial"
    assert job["result"]["failed_tasks"][0]["sendtask_id"] == "Task B"