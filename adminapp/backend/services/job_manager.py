import asyncio
import uuid
from typing import Callable, Dict, List, Optional
from datetime import datetime, timezone
from backend.services.log_manager import Logger
from backend.repository.db_controller import db_controller
from backend.repository.models import JobRun, JobRunItem
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func as sql_func

logger = Logger().get_logger()

class JobManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance.jobs = {}  # job_id -> process-local asyncio task metadata
            cls._instance.semaphore = asyncio.Semaphore(4)
        return cls._instance

    def get_current_job(self, username: str) -> Optional[Dict]:
        owner_jobs = [
            job for job in self.jobs.values()
            if job["owner_username"] == username
        ]
        if not owner_jobs:
            return None
        return max(owner_jobs, key=lambda job: job["start_time"])

    async def start_job(
        self,
        username: str,
        job_type: str,
        task_func: Callable,
        *args,
        job_code: Optional[str] = None,
        items: Optional[List[Dict[str, str]]] = None,
        request_params: Optional[Dict] = None,
        **kwargs,
    ):
        job_id = str(uuid.uuid4())
        requested_items = self._deduplicate_items(items or [])
        display_name = self._display_name(job_type, requested_items)

        await db_controller.create(JobRun, {
            "job_id": job_id,
            "source": "manual",
            "job_code": job_code,
            "job_type": job_type,
            "display_name": display_name,
            "owner_username": username,
            "status": "pending",
            "message": f"正在執行：{display_name}",
            "request_params": request_params or {},
        })

        accepted_items, excluded_items = await self._claim_items(job_id, requested_items)
        if not accepted_items and requested_items:
            result = {
                "updated_count": 0,
                "successful_tasks": [],
                "skipped_count": len(excluded_items),
                "skipped_tasks": excluded_items,
                "failed_count": 0,
                "failed_tasks": [],
            }
            await db_controller.update(JobRun, {"job_id": job_id}, {
                "status": "completed",
                "result": result,
                "finished_at": sql_func.now(),
            })
            return {"job_id": job_id, "accepted": [], "excluded": excluded_items}

        async def wrapper():
            try:
                await db_controller.update(JobRun, {"job_id": job_id}, {"status": "running"})
                self.jobs[job_id]["status"] = "running"
                async with self.semaphore:
                    if requested_items:
                        result = await task_func(*args, accepted_items=accepted_items, job_id=job_id, **kwargs)
                    else:
                        result = await task_func(*args, **kwargs)
                result = result if isinstance(result, dict) else {}
                if excluded_items:
                    result.setdefault("skipped_tasks", []).extend(excluded_items)
                    result["skipped_count"] = len(result["skipped_tasks"])
                job_status = result.get("job_status", "completed")
                if job_status not in {"completed", "partial", "failed"}:
                    raise ValueError(f"Unsupported job status: {job_status}")
                await db_controller.update(JobRun, {"job_id": job_id}, {
                    "status": job_status,
                    "result": result,
                    "error": result.get("error_summary"),
                    "finished_at": sql_func.now(),
                })
                self.jobs[job_id].update(status=job_status, result=result, error=result.get("error_summary"))
            except asyncio.CancelledError:
                await self._finish_pending_items(job_id, "cancelled", "cancelled")
                await db_controller.update(JobRun, {"job_id": job_id}, {
                    "status": "cancelled",
                    "finished_at": sql_func.now(),
                })
                self.jobs[job_id]["status"] = "cancelled"
                raise
            except Exception as error:
                logger.error(f"Job {job_id} ({job_type}) failed for {username}: {error}")
                await self._finish_pending_items(job_id, "failed", str(error))
                await db_controller.update(JobRun, {"job_id": job_id}, {
                    "status": "failed",
                    "error": str(error),
                    "finished_at": sql_func.now(),
                })
                self.jobs[job_id].update(status="failed", error=str(error))

        task = asyncio.create_task(wrapper())
        self.jobs[job_id] = {
            "job_id": job_id,
            "owner_username": username,
            "type": job_type,
            "status": "pending",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "message": f"正在執行：{display_name}",
        }
        return {"job_id": job_id, "accepted": accepted_items, "excluded": excluded_items}

    async def cancel_job(self, username: str, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job["owner_username"] != username or job["task"].done():
            return False
        job["task"].cancel()
        return True

    async def mark_item(self, job_id: str, sendtask_uuid: str, status: str, reason: Optional[str] = None):
        values = {"status": status}
        if status == "running":
            values["started_at"] = sql_func.now()
        if status in {"completed", "failed", "skipped", "cancelled"}:
            values["finished_at"] = sql_func.now()
        if reason is not None:
            values["reason"] = reason
        await db_controller.update(JobRunItem, {"job_id": job_id, "sendtask_uuid": sendtask_uuid}, values)

    async def _claim_items(self, job_id: str, items: List[Dict[str, str]]):
        accepted, excluded = [], []
        for item in items:
            try:
                await db_controller.create(JobRunItem, {
                    "job_id": job_id,
                    "sendtask_uuid": item["sendtask_uuid"],
                    "sendtask_id": item["sendtask_id"],
                    "status": "pending",
                })
                accepted.append(item)
            except IntegrityError:
                excluded_item = {**item, "reason": "duplicate_active"}
                await self._record_excluded_item(job_id, excluded_item)
                excluded.append(excluded_item)
            except Exception as error:
                logger.error(f"Failed to claim {item['sendtask_uuid']} for job {job_id}: {error}")
                excluded_item = {**item, "reason": "claim_failed"}
                await self._record_excluded_item(job_id, excluded_item)
                excluded.append(excluded_item)
        return accepted, excluded

    async def _record_excluded_item(self, job_id: str, item: Dict[str, str]):
        await db_controller.create(JobRunItem, {
            "job_id": job_id,
            "sendtask_uuid": item["sendtask_uuid"],
            "sendtask_id": item["sendtask_id"],
            "status": "skipped",
            "reason": item["reason"],
            "finished_at": sql_func.now(),
        })

    async def _finish_pending_items(self, job_id: str, status: str, reason: str):
        await db_controller.update(
            JobRunItem,
            {"job_id": job_id, "status": ["pending", "running"]},
            {"status": status, "reason": reason, "finished_at": sql_func.now()},
        )

    @staticmethod
    def _deduplicate_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        seen = set()
        unique = []
        for item in items:
            task_uuid = item["sendtask_uuid"]
            if task_uuid not in seen:
                seen.add(task_uuid)
                unique.append(item)
        return unique

    @staticmethod
    def _display_name(job_type: str, items: List[Dict[str, str]]) -> str:
        if not items:
            return job_type
        names = [item["sendtask_id"] for item in items]
        suffix = "、".join(names[:3])
        if len(names) > 3:
            suffix += f" 等 {len(names)} 筆"
        return f"{job_type}：{suffix}"
