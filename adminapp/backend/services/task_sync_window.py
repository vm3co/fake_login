from contextvars import ContextVar
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from backend.services.se2_task_reader import normalize_timestamp


automatic_sync = ContextVar('automatic_task_sync', default=False)
TAIPEI = ZoneInfo('Asia/Taipei')


def automatic_task_sync(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        token = automatic_sync.set(True)
        try:
            return await function(*args, **kwargs)
        finally:
            automatic_sync.reset(token)
    return wrapped


def sync_window_closed(task, metadata, now):
    stop = metadata['stop_time_new']
    end = stop if stop not in (None, 0, -1, '0', '-1') else task.get(
        'pre_test_end_ut' if task['pre_test_enable'] else 'test_end_ut')
    if end in (None, 0, -1, '0', '-1'):
        return False
    end = normalize_timestamp(end)
    deadline = datetime.combine(
        datetime.fromtimestamp(end, TAIPEI).date() + timedelta(days=2),
        datetime.min.time(), TAIPEI,
    )
    return now >= deadline.timestamp()