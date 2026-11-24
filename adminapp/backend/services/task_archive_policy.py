from collections.abc import Mapping

from backend.services.se2_task_reader import TaskReadError, normalize_timestamp


ARCHIVE_DAYS = 14
END_TIME_FIELDS = ("test_end_ut", "pre_test_end_ut", "stop_time_new")


def should_archive_task(task, *, now: int) -> bool:
    cutoff = normalize_timestamp(now) - ARCHIVE_DAYS * 86400
    values = []
    for field in END_TIME_FIELDS:
        value = task.get(field) if isinstance(task, Mapping) else getattr(task, field, None)
        if value is None or (not isinstance(value, bool) and value in (0, -1, "0", "-1")):
            continue
        try:
            values.append(normalize_timestamp(value))
        except TaskReadError:
            raise TaskReadError("invalid_task_end_time") from None
    return bool(values) and all(value < cutoff for value in values)