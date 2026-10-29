import asyncio
import os
import uuid
from datetime import timedelta
from typing import Awaitable, Callable, Dict, Optional

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import aliased

from backend.repository.database import async_session
from backend.repository.models import JobRun
from backend.services.log_manager import Logger

logger = Logger().get_logger()

ACTIVE_STATUSES = ("queued", "claiming", "running", "cancel_requested")


class JobQueue:
    def __init__(self):
        self.worker_id = f"{os.getpid()}-{uuid.uuid4()}"
        self.handlers: Dict[str, Callable[[str], Awaitable[dict]]] = {}
        self.job_handlers: Dict[str, Callable[[str], Awaitable[dict]]] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._worker_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(4)

    def register(self, job_code: str, handler: Callable[[str], Awaitable[dict]]):
        self.handlers[job_code] = handler

    def register_job(self, job_id: str, handler: Callable[[str], Awaitable[dict]]):
        self.job_handlers[job_id] = handler

    async def start(self):
        if self._worker_task and not self._worker_task.done():
            return
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        if self._worker_task:
            await self._worker_task
        for task in self.running_tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)

    def wake(self):
        self._wake_event.set()

    async def cancel(self, username: str, job_id: str) -> str:
        async with async_session() as session:
            result = await session.execute(
                select(JobRun).where(JobRun.job_id == job_id).with_for_update()
            )
            job = result.scalar_one_or_none()
            if not job or job.source != "manual" or job.owner_username != username:
                return "not_found"
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = func.now()
                await session.commit()
                self.wake()
                return "cancelled"
            if job.status in {"claiming", "running"}:
                job.status = "cancel_requested"
                job.cancel_requested_at = func.now()
                await session.commit()
                task = self.running_tasks.get(job_id)
                if task and not task.done():
                    task.cancel()
                return "requested"
            return "finished"

    async def _worker_loop(self):
        while not self._stop_event.is_set():
            claimed_any = False
            while not self._stop_event.is_set():
                job = await self._claim_next()
                if not job:
                    break
                claimed_any = True
                task = asyncio.create_task(self._run_claimed(job.job_id, job.job_code))
                self.running_tasks[job.job_id] = task
                task.add_done_callback(lambda _task, job_id=job.job_id: self.running_tasks.pop(job_id, None))
            if not claimed_any:
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                self._wake_event.clear()

    async def _claim_next(self):
        async with async_session() as session:
            async with session.begin():
                earlier_exclusive = aliased(JobRun)
                active_exclusive = exists().where(and_(
                    JobRun.status.in_(("claiming", "running", "cancel_requested")),
                    JobRun.execution_class == "maintenance_exclusive",
                ))
                active_manual = exists().where(and_(
                    JobRun.status.in_(("claiming", "running", "cancel_requested")),
                    JobRun.execution_class == "manual_shared",
                ))

                stmt = (
                    select(JobRun)
                    .where(
                        JobRun.status == "queued",
                        JobRun.available_at <= func.now(),
                        or_(
                            JobRun.job_code.in_(tuple(self.handlers.keys()) or ("__none__",)),
                            JobRun.job_id.in_(tuple(self.job_handlers.keys()) or ("__none__",)),
                        ),
                        or_(
                            and_(
                                JobRun.execution_class == "maintenance_exclusive",
                                ~active_exclusive,
                                ~active_manual,
                            ),
                            and_(
                                JobRun.execution_class == "manual_shared",
                                ~active_exclusive,
                                ~exists().where(and_(
                                    earlier_exclusive.status == "queued",
                                    earlier_exclusive.execution_class == "maintenance_exclusive",
                                    earlier_exclusive.queue_sequence < JobRun.queue_sequence,
                                )),
                            ),
                            JobRun.execution_class.in_(("scheduler_itemized", "lightweight")),
                        ),
                    )
                    .order_by(JobRun.priority.desc(), JobRun.queue_sequence.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                result = await session.execute(stmt)
                job = result.scalar_one_or_none()
                if not job:
                    return None

                job.status = "claiming"
                job.claimed_by = self.worker_id
                job.heartbeat_at = func.now()
                job.lease_expires_at = func.now() + timedelta(minutes=10)
                job.attempt_count += 1
                await session.flush()
                return job

    async def _run_claimed(self, job_id: str, job_code: str):
        handler = self.job_handlers.pop(job_id, None) or self.handlers.get(job_code)
        if not handler:
            await self._finish(job_id, "failed", error=f"No handler registered for {job_code}")
            return
        async with self._semaphore:
            try:
                await self._set_running(job_id)
                result = await handler(job_id)
                status = result.get("job_status", "completed") if isinstance(result, dict) else "completed"
                await self._finish(job_id, status, result=result)
            except asyncio.CancelledError:
                await self._finish(job_id, "cancelled")
            except Exception as error:
                logger.error(f"Queued job {job_id} failed: {error}")
                await self._finish(job_id, "failed", error=str(error))
            finally:
                self.wake()

    async def _set_running(self, job_id: str):
        async with async_session() as session:
            await session.execute(
                update(JobRun)
                .where(JobRun.job_id == job_id, JobRun.claimed_by == self.worker_id)
                .values(status="running", heartbeat_at=func.now(), lease_expires_at=func.now() + timedelta(minutes=10))
            )
            await session.commit()

    async def _finish(self, job_id: str, status: str, result: Optional[dict] = None, error: Optional[str] = None):
        async with async_session() as session:
            await session.execute(
                update(JobRun)
                .where(JobRun.job_id == job_id, JobRun.claimed_by == self.worker_id)
                .values(
                    status=status,
                    result=result,
                    error=error or (result or {}).get("error_summary"),
                    finished_at=func.now(),
                    lease_expires_at=None,
                    heartbeat_at=func.now(),
                )
            )
            await session.commit()


job_queue = JobQueue()
