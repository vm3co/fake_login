import asyncio
import uuid
from typing import Dict, Optional, Callable, Any
from datetime import datetime
from backend.services.log_manager import Logger

logger = Logger().get_logger()

class JobManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance.jobs = {}  # username -> {job_id, task, status, type, start_time, message}
        return cls._instance

    def get_current_job(self, username: str) -> Optional[Dict]:
        return self.jobs.get(username)

    async def start_job(self, username: str, job_type: str, func: Callable, *args, **kwargs):
        current_job = self.jobs.get(username)
        if current_job and not current_job['task'].done():
            raise Exception("已有任務正在執行中，請先等待完成或取消")

        job_id = str(uuid.uuid4())
        
        async def wrapper():
            try:
                self.jobs[username]['status'] = 'running'
                logger.info(f"Job {job_id} ({job_type}) started for {username}")
                result = await func(*args, **kwargs)
                self.jobs[username]['status'] = 'completed'
                self.jobs[username]['result'] = result
                logger.info(f"Job {job_id} ({job_type}) completed for {username}")
            except asyncio.CancelledError:
                self.jobs[username]['status'] = 'cancelled'
                logger.info(f"Job {job_id} ({job_type}) cancelled for {username}")
                raise
            except Exception as e:
                self.jobs[username]['status'] = 'failed'
                self.jobs[username]['error'] = str(e)
                logger.error(f"Job {job_id} ({job_type}) failed for {username}: {e}")
            finally:
                # Keep the job state for a while so frontend can query result, 
                # but for simplicity in this version, we might just leave it there 
                # until next job starts or user clears it?
                # Or maybe auto-clear after some time? 
                # For now, let's keep it.
                pass

        task = asyncio.create_task(wrapper())
        
        self.jobs[username] = {
            'job_id': job_id,
            'type': job_type,
            'status': 'pending',
            'start_time': datetime.now().isoformat(),
            'task': task,
            'message': f"正在執行：{job_type}..."
        }
        
        return job_id

    async def cancel_job(self, username: str):
        current_job = self.jobs.get(username)
        if current_job and not current_job['task'].done():
            current_job['task'].cancel()
            try:
                await current_job['task']
            except asyncio.CancelledError:
                pass
            return True
        return False
