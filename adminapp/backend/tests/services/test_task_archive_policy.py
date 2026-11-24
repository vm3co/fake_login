import pytest

from backend.services.se2_task_reader import TaskReadError
from backend.services.task_archive_policy import should_archive_task


NOW = 1800000000
CUTOFF = NOW - 14 * 86400


@pytest.mark.parametrize("task,expected", [
    ({}, False),
    ({"test_end_ut": None, "pre_test_end_ut": 0, "stop_time_new": -1}, False),
    ({"test_end_ut": NOW - 7 * 86400}, False),
    ({"test_end_ut": CUTOFF}, False),
    ({"test_end_ut": CUTOFF - 1}, True),
    ({"test_end_ut": CUTOFF - 1, "pre_test_end_ut": NOW}, False),
    ({"test_end_ut": CUTOFF - 1, "stop_time_new": NOW + 86400}, False),
    ({"pre_test_end_ut": str(CUTOFF - 1), "stop_time_new": "-1"}, True),
    ({"test_end_ut": CUTOFF - 1, "pre_test_end_ut": CUTOFF - 2, "stop_time_new": "0"}, True),
])
def test_fourteen_day_policy(task, expected):
    assert should_archive_task(task, now=NOW) is expected


@pytest.mark.parametrize("value", [True, False, "bad", "", [], -2, 1.5, float("inf")])
def test_malformed_times_are_not_evidence_for_archiving(value):
    with pytest.raises(TaskReadError, match="invalid_task_end_time"):
        should_archive_task({"test_end_ut": CUTOFF - 1, "stop_time_new": value}, now=NOW)