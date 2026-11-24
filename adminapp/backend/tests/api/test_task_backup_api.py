from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import insert, select, delete

from backend.repository.models import TaskBackup
from backend.services.task_backup_access import backup_scope, require_backup_access
from backend.tests.repository.test_task_backup_schema import schema_engine, backup_values
from backend.tests.services.test_task_backup_transfer import setup_transfer
from unittest.mock import AsyncMock, patch
from backend.services.task_sync import read_expected_task_version, task_sync_transaction, transfer_task_to_backup


@pytest.mark.asyncio
async def test_backup_access_uses_snapshot_org_not_current_task_org(schema_engine):
    factory, engine, _ = await setup_transfer(schema_engine)
    backup_id = str(uuid4())
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(**backup_values(
            "old-generation", backup_id=backup_id, owner_gids=["old-org"],
        )))
    async with factory() as session:
        assert (await require_backup_access(session, backup_id, ("old-org",))).backup_id == backup_id
        assert (await require_backup_access(session, backup_id, None)).backup_id == backup_id
        for requested in (backup_id, "task-1"):
            with pytest.raises(HTTPException) as error:
                await require_backup_access(session, requested, ("org-1",))
            assert error.value.status_code == 404


@pytest.mark.parametrize("identity", [
    {"user_type": "customer", "admin_role": True},
    {"user_type": "user", "orgs": []}, {"user_type": "user", "orgs": "org-1"},
    {"user_type": "user", "orgs": [None]}, {"user_type": "other", "orgs": ["org-1"]},
])
def test_backup_scope_rejects_untrusted_or_empty_scope(identity):
    with pytest.raises(HTTPException) as error:
        backup_scope(identity)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_backup_endpoints_read_export_and_delete_exact_snapshot(async_client, schema_engine):
    from backend.api import task_backup_api
    from backend.api.user_api import get_current_user
    from backend.main import app
    from io import BytesIO
    from openpyxl import load_workbook

    factory, _, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, expected) as locked:
        transferred = await transfer_task_to_backup(locked, reason="manual_reload")
    backup_id = transferred.backup_id
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "username": "user-a", "orgs": ["org-1"]}
    try:
        with patch.object(task_backup_api, "async_session", factory):
            listing = await async_client.get("/api/task_backups")
            assert listing.status_code == 200, listing.text
            assert listing.json()["total_count"] == 1 and listing.json()["data"][0]["detail_count"] == 2
            header = await async_client.get(f"/api/task_backups/{backup_id}")
            assert header.status_code == 200 and header.json()["data"]["task_snapshot"]["sendtask_id"] == "Original"
            response = await async_client.post(f"/api/task_backups/{backup_id}/details", json={})
            assert response.status_code == 200, response.text
            assert response.json()["data"][0]["second_input_time"] == [70, 80]
            assert response.json()["data"][0]["display"]["second_input_count"] == 2
            exported = await async_client.get(f"/api/task_backups/{backup_id}/export.xlsx")
            assert exported.status_code == 200, exported.text
            workbook = load_workbook(BytesIO(exported.content))
            assert workbook["details"].max_row == 3
            templates = dict(workbook["templates"].iter_rows(min_row=2, values_only=True))
            assert "Original subject" in templates["template-1"]
            assert templates["missing"] is None
            assert backup_id in exported.headers["content-disposition"]
            refused = await async_client.delete(f"/api/task_backups/{backup_id}")
            assert refused.status_code == 400
            deleted = await async_client.delete(f"/api/task_backups/{backup_id}?confirm_delete=true")
            assert deleted.status_code == 200
            assert (await async_client.get(f"/api/task_backups/{backup_id}")).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["list", "header", "details", "export", "delete"])
@pytest.mark.parametrize("identity,expected", [
    ({"user_type": "user", "admin_role": True}, 200),
    ({"user_type": "user", "orgs": ["old-org"]}, 200),
    ({"user_type": "user", "orgs": ["org-1"]}, 404),
    ({"user_type": "user", "orgs": []}, 403),
    ({"user_type": "customer", "admin_role": True}, 403),
    (None, 401),
])
async def test_every_backup_endpoint_enforces_identity_matrix(async_client, schema_engine, endpoint, identity, expected):
    from backend.api import task_backup_api
    from backend.api.user_api import get_current_user
    from backend.main import app

    factory, engine, _ = await setup_transfer(schema_engine)
    backup_id = str(uuid4())
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(**backup_values("old", backup_id=backup_id, owner_gids=["old-org"])))
    if identity is not None:
        app.dependency_overrides[get_current_user] = lambda: identity
    try:
        with patch.object(task_backup_api, "async_session", factory):
            path = f"/api/task_backups/{backup_id}"
            if endpoint == "list":
                response = await async_client.get("/api/task_backups")
                if expected == 404:
                    expected = 200
                    assert response.json()["total_count"] == 0 and response.json()["data"] == []
            elif endpoint == "details":
                response = await async_client.post(path + "/details", json={})
                if expected == 200:
                    assert response.json()["data"] == [] and response.json()["total_count"] == 0
            elif endpoint == "export":
                response = await async_client.get(path + "/export.xlsx")
            elif endpoint == "delete":
                response = await async_client.delete(path + "?confirm_delete=true")
            else:
                response = await async_client.get(path)
        assert response.status_code == expected, response.text[:200]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_versions_filters_and_delete_do_not_touch_current_or_other_backup(async_client, schema_engine):
    from backend.api import task_backup_api
    from backend.api.user_api import get_current_user
    from backend.main import app
    from backend.repository.models import TaskBackupDetail, Mtmpl, SendTask, CustomerTask, CustomerAcct
    from datetime import datetime, timezone
    from io import BytesIO
    from openpyxl import load_workbook
    import json

    factory, engine, _ = await setup_transfer(schema_engine)
    expected = await read_expected_task_version(factory, "task-1")
    async with task_sync_transaction(factory, expected) as locked:
        first = await transfer_task_to_backup(locked, reason="manual_reload")
    second = str(uuid4())
    async with engine.begin() as conn:
        await conn.execute(insert(TaskBackup).values(**backup_values("second", backup_id=second, reason="remote_recreated",
            latest_remote_status="present", recreated_detected_at=datetime.now(timezone.utc))))
        await conn.execute(insert(TaskBackupDetail).values(backup_id=second, uuid="old-log-1", sendtask_uuid="task-1",
            target_email="unique@example.test", send_time=1735660800, send_res="True", plan_time=100,
            second_input_info=["=" + "x" * 40000]))
        await conn.execute(insert(SendTask).values(sendtask_uuid="task-1", sendtask_id="New", sendtask_owner_gid=["org-2"]))
        await conn.execute(delete(Mtmpl))
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "orgs": ["org-1"]}
    try:
        with patch.object(task_backup_api, "async_session", factory):
            listing = await async_client.get("/api/task_backups?recreated=true&remote_status=present&page_size=1")
            assert listing.json()["total_count"] == 1 and listing.json()["data"][0]["backup_id"] == second
            assert "task_snapshot" not in listing.json()["data"][0]
            response = await async_client.post(f"/api/task_backups/{second}/details", json={
                "dateFrom": "2025-01-01", "dateTo": "2025-01-01", "resultType": "send", "searchText": "unique",
            })
            assert response.json()["total_count"] == 1
            wrong_date = await async_client.post(f"/api/task_backups/{second}/details", json={"dateTo": "2024-12-31"})
            assert wrong_date.json()["total_count"] == 0
            exported = await async_client.get(f"/api/task_backups/{first.backup_id}/export.xlsx")
            book = load_workbook(BytesIO(exported.content))
            templates = dict(book["templates"].iter_rows(min_row=2, values_only=True))
            assert "Original subject" in templates["template-1"]
            assert dict(book["stats"].iter_rows(min_row=2, values_only=True))["todayfailed"] == 1
            large = await async_client.get(f"/api/task_backups/{second}/export.xlsx")
            book = load_workbook(BytesIO(large.content))
            chunks = list(book["overflow"].iter_rows(min_row=2, values_only=True))
            rebuilt = "".join(row[4] for row in sorted(chunks, key=lambda row: row[3]))
            assert json.loads(rebuilt) == ["=" + "x" * 40000]
            assert (await async_client.get("/api/task_backups/task-1")).status_code == 404
            assert (await async_client.delete(f"/api/task_backups/{first.backup_id}?confirm_delete=true")).status_code == 200
            assert (await async_client.get(f"/api/task_backups/{second}")).status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    async with factory() as session:
        assert await session.scalar(select(SendTask.sendtask_id)) == "New"
        assert await session.scalar(select(CustomerTask.customer_uuid)) == "customer-1"
        assert await session.scalar(select(CustomerAcct.sendtasks)) == [{"uuid": "task-1"}]
        assert len((await session.scalars(select(TaskBackupDetail))).all()) == 1


def test_excel_formula_strings_remain_text():
    from backend.services.excel_utils import backup_workbook
    from openpyxl import load_workbook
    from io import BytesIO

    data = {"backup_id": "backup", "task_snapshot": {"name": "=1+1"}, "stats_snapshot": None, "mail_template_snapshot": {}}
    book = load_workbook(BytesIO(backup_workbook(data, [])))
    assert book["task"].cell(2, 2).value == "=1+1" and book["task"].cell(2, 2).data_type == "s"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"page": 0}, {"rowsPerPage": 201}, {"acctControl": [True]}, {"resultType": "invalid"},
    {"sortBy": "__table__"}, {"sort": "invalid"}, {"dateFrom": "bad-date"},
    {"dateFrom": "2025-01-02", "dateTo": "2025-01-01"}, {"sendtask_uuid": "task-1"}, {"paginate": False},
])
async def test_backup_details_reject_invalid_parameters(async_client, body):
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "orgs": ["org-1"]}
    try:
        response = await async_client.post("/api/task_backups/unused/details", json=body)
        assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_backup_pagination_ip_projection_preserves_raw_snapshot(async_client, schema_engine):
    from backend.api import task_backup_api
    from backend.api.user_api import get_current_user
    from backend.main import app
    from backend.repository.models import TaskBackupDetail
    from sqlalchemy import update

    factory, engine, _ = await setup_transfer(schema_engine)
    async with task_sync_transaction(factory, await read_expected_task_version(factory, "task-1")) as locked:
        transferred = await transfer_task_to_backup(locked, reason="remote_missing")
    async with engine.begin() as conn:
        await conn.execute(update(TaskBackupDetail).values(
            access_src=["10.0.0.1", "192.0.2.1"], access_time=[10, 20], access_dev=["first", "last"],
        ))
    app.dependency_overrides[get_current_user] = lambda: {"user_type": "user", "orgs": ["org-1"]}
    try:
        with patch.object(task_backup_api, "async_session", factory):
            path = f"/api/task_backups/{transferred.backup_id}/details"
            first = await async_client.post(path, json={"rowsPerPage": 1, "page": 1, "sort": "asc", "sortBy": "uuid", "filterIp": "10.*"})
            second = await async_client.post(path, json={"rowsPerPage": 1, "page": 2, "sort": "asc", "sortBy": "uuid"})
            row = first.json()["data"][0]
            assert first.json()["total_count"] == second.json()["total_count"] == 2
            assert row["uuid"] != second.json()["data"][0]["uuid"]
            assert row["access_time"] == [10, 20] and row["display"]["access_count"] == 1
            assert row["display"]["access_src"] == "192.0.2.1"
            beyond = await async_client.post(path, json={"page": 3, "rowsPerPage": 1})
            assert beyond.json()["data"] == [] and beyond.json()["total_count"] == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    async with factory() as session:
        assert (await session.scalars(select(TaskBackupDetail.access_time))).all() == [[10, 20], [10, 20]]