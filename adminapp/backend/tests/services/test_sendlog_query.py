from types import SimpleNamespace
from copy import deepcopy

import pytest
from sqlalchemy import insert

from backend.repository.models import SendLogDetail, TaskBackup, TaskBackupDetail
from backend.services.sendlog_query import project_events, sendlog_query
from backend.tests.repository.test_task_backup_schema import schema_engine, backup_values
from backend.tests.services.test_task_backup_transfer import setup_transfer


def options(**overrides):
    return SimpleNamespace(**{
        "searchText": None, "dateFrom": None, "dateTo": None, "acctControl": [True] * 5,
        "resultType": "all", "showAccessed": False, "showClicked": False, "showFiled": False,
        "sort": "asc", "sortBy": "plan_time", "page": 1, "rowsPerPage": 20, "paginate": True,
        **overrides,
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("filters,expected", [({}, 2), ({"searchText": "absent"}, 0), ({"showAccessed": True}, 2),
                                                       ({"acctControl": [False] * 5}, 0), ({"resultType": "notyet"}, 2)])
async def test_query_supports_current_and_backup_sources(schema_engine, filters, expected):
    factory, engine, _ = await setup_transfer(schema_engine)
    async with engine.begin() as conn:
        backup_id = await conn.scalar(insert(TaskBackup).values(**backup_values("old")).returning(TaskBackup.backup_id))
        await conn.execute(insert(TaskBackupDetail), [{"backup_id": backup_id, "uuid": f"copy-{number}", "sendtask_uuid": "task-1",
            "target_email": "same@example.test", "plan_time": 100, "access_time": [10, 20]} for number in (1, 2)])
    async with factory() as session:
        for model, condition in ((SendLogDetail, SendLogDetail.sendtask_uuid == "task-1"), (TaskBackupDetail, TaskBackupDetail.backup_id == backup_id)):
            statement, count = sendlog_query(model, condition, options(**filters))
            assert await session.scalar(count) == expected
            assert len((await session.scalars(statement)).all()) == expected


def test_event_projection_keeps_snapshot_and_array_alignment():
    raw = {"access_time": [1, 2, 3], "access_src": ["10.1.1.1", "192.0.2.1", "10.2.1.1"], "access_dev": ["a", "b", "c"],
           "second_input_time": [4, 5], "second_input_src": ["2001:db8::1", "2001:db8::2"], "second_input_info": ["first", "second"]}
    original = deepcopy(raw)
    projected = project_events(raw, "10.*,2001:db8::1")
    assert projected["access_count"] == 1 and projected["access_time"] == 2 and projected["access_dev"] == "b"
    assert projected["second_input_count"] == 1 and projected["second_input_info"] == "second"
    assert raw == original