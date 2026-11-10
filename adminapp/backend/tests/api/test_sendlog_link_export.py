import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from openpyxl import load_workbook

from backend.api.data_api import build_sendlog_event_urls
from backend.api.user_api import get_current_user
from backend.main import app
from backend.repository.models import SendLogDetail, SendTask


TASK_UUID = "d9d4bec84b8441e7a954c45e94cd7d32"
PERSON_UUID = "f9f6edb1be0e35aca4059306ea0f7bd6"
TOKEN = "a4059306ea0f7bd6d9d4bec84b8441e7a954c45e94cd7d32f9f6edb1be0e35ac"


def test_exact_urls_and_round_trip():
    urls = build_sendlog_event_urls({"uuid": PERSON_UUID, "sendtask_uuid": TASK_UUID})
    assert list(urls.values()) == [
        f"https://link.acsicook.info/a/{event}/{TOKEN}" for event in ("a", "l", "f")
    ]
    for url in urls.values():
        token = url.rsplit("/", 1)[1]
        assert len(token) == 64
        assert token[16:48] == TASK_UUID
        assert token[48:] + token[:16] == PERSON_UUID


@pytest.mark.parametrize("field", ["uuid", "sendtask_uuid"])
@pytest.mark.parametrize("invalid", [None, "", 123, "a" * 31, "a" * 33, "a" * 36, "g" * 32])
def test_invalid_identity_rejected(field, invalid):
    row = {"uuid": PERSON_UUID, "sendtask_uuid": TASK_UUID, field: invalid}
    with pytest.raises(ValueError):
        build_sendlog_event_urls(row)


@pytest.fixture
def export_user():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: {
        "user_type": "user", "admin_role": False, "orgs": ["org-1"]
    }
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def make_detail(recipient_uuid):
    return SendLogDetail(
        uuid=recipient_uuid, sendtask_uuid=TASK_UUID, target_email="same@example.com",
        person_info="Test", send_time=1700000000, send_res="True",
        access_time=[1700000000, 1700000001], access_src=[None, "127.0.0.1"],
        second_input_time=[], second_input_info=[None],
    )


@pytest.mark.asyncio
async def test_new_export_preserves_old_report_and_all_rows(async_client, export_user):
    rows = [make_detail(PERSON_UUID), make_detail("0123456789abcdef0123456789abcdef")]
    task = SimpleNamespace(sendtask_owner_gid=["org-1"])

    async def get_rows(model, **kwargs):
        if model is SendLogDetail:
            assert kwargs == {"filters": {"sendtask_uuid": TASK_UUID}}
            return rows
        return []

    with patch("backend.api.data_api.db_controller.get_one", new=AsyncMock(return_value=task)) as get_task, \
         patch("backend.api.data_api.db_controller.get", new=AsyncMock(side_effect=get_rows)):
        body = {"sendtask_uuid": TASK_UUID, "name": "Test report"}
        original = await async_client.post("/api/download_sendlog_xlsx", json=body)
        linked = await async_client.post("/api/download_sendlog_links_xlsx", json=body)

    get_task.assert_awaited_with(SendTask, {"sendtask_uuid": TASK_UUID})
    assert original.status_code == linked.status_code == 200
    assert "spreadsheetml.sheet" in linked.headers["content-type"]
    assert "filename*=UTF-8''" in linked.headers["content-disposition"]
    old_frame = pd.read_excel(io.BytesIO(original.content))
    new_frame = pd.read_excel(io.BytesIO(linked.content))
    pd.testing.assert_frame_equal(old_frame, new_frame.iloc[:, :-3])
    assert len(new_frame) == 2
    expected_urls = build_sendlog_event_urls({"uuid": PERSON_UUID, "sendtask_uuid": TASK_UUID})
    assert new_frame.columns[-3:].tolist() == list(expected_urls)
    assert new_frame.iloc[0, -3:].tolist() == list(expected_urls.values())
    assert new_frame.iloc[0, -3] != new_frame.iloc[1, -3]
    workbook = load_workbook(io.BytesIO(linked.content))
    for row in workbook.active.iter_rows(min_row=2, min_col=len(new_frame.columns) - 2):
        assert all(cell.data_type == "s" for cell in row)


@pytest.mark.asyncio
@pytest.mark.parametrize("rows,status", [([], 404), ([make_detail("invalid")], 422)])
async def test_empty_and_invalid_exports(async_client, export_user, rows, status):
    task = SimpleNamespace(sendtask_owner_gid=["org-1"])
    with patch("backend.api.data_api.db_controller.get_one", new=AsyncMock(return_value=task)), \
         patch("backend.api.data_api.db_controller.get", new=AsyncMock(return_value=rows)):
        response = await async_client.post("/api/download_sendlog_links_xlsx", json={
            "sendtask_uuid": TASK_UUID, "name": "Test"
        })
    assert response.status_code == status
    if status == 422:
        assert "uuid" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("task,status", [(None, 404), (SimpleNamespace(sendtask_owner_gid=["org-2"]), 403)])
async def test_access_checked_before_reading_rows(async_client, export_user, task, status):
    with patch("backend.api.data_api.db_controller.get_one", new=AsyncMock(return_value=task)), \
         patch("backend.api.data_api.db_controller.get", new=AsyncMock()) as get_rows:
        response = await async_client.post("/api/download_sendlog_links_xlsx", json={
            "sendtask_uuid": TASK_UUID, "name": "Test"
        })
    assert response.status_code == status
    get_rows.assert_not_awaited()