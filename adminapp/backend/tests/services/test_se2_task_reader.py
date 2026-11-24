import json

import httpx
import pytest

from backend.services.se2_task_reader import (
    SE2TaskReader, TaskNotFound, TaskReadError, TaskVersionChanged, normalize_timestamp,
)


def task_body(create_ut=100):
    return {
        "data": {
            "sendtask_uuid": "task-1", "sendtask_id": "Test", "sendtask_owner_gid": ["org-1"],
            "sendtask_create_ut": create_ut, "pre_test_enable": False,
        },
        "metadata": {"pause": False, "stop_time_new": -1, "summary": {"person_count": 1}},
    }


def reader(handler):
    return SE2TaskReader("https://se2.test", lambda: {}, False, transport=httpx.MockTransport(handler))


def sendlog_record(uuid="log-1"):
    return {
        "uuid": uuid, "target_email": "test@example.test", "person_info": "Test",
        "template_uuid": "template-1", "plan_time": "100", "send_time": 0, "send_res": "",
        **{field: [] for field in (
            "access_time", "access_src", "access_dev", "click_time", "click_src",
            "click_dev", "file_time", "file_src", "file_dev",
        )},
    }


@pytest.mark.asyncio
async def test_missing_requires_http_status_business_code_endpoint_and_verified_mode():
    service = reader(lambda request: httpx.Response(404, json={"message": "missing", "sub_code": 40400}))
    with pytest.raises(TaskNotFound):
        await service.read_sendtask("task-1")
    with pytest.raises(TaskReadError) as error:
        await service.read_sendtask("task-1", sendlog_type="pretest")
    assert type(error.value) is TaskReadError
    with pytest.raises(TaskReadError) as error:
        await service.read_sendtasks()
    assert type(error.value) is TaskReadError


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [
    (404, {"message": "route missing"}), (403, {"sub_code": 40400}),
    (401, {"error": "expired"}), (500, {"sub_code": 40400}),
    (200, {"sub_code": 40400}), (200, []), (200, {}),
])
async def test_errors_never_become_missing_or_success(status, body):
    service = reader(lambda request: httpx.Response(status, json=body))
    with pytest.raises(TaskReadError) as error:
        await service.read_sendtask("task-1")
    assert type(error.value) is TaskReadError


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"<html>login</html>", b"{broken"])
async def test_non_json_is_failure(body):
    service = reader(lambda request: httpx.Response(200, content=body))
    with pytest.raises(TaskReadError, match="invalid_json"):
        await service.read_sendtask("task-1")


@pytest.mark.asyncio
async def test_transport_error_is_not_empty_or_fallback():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("private details", request=request)

    with pytest.raises(TaskReadError, match="transport_error"):
        await reader(handler).read_sendtask("task-1")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_success_normalizes_version_without_mutating_response():
    body = task_body("100")
    result = await reader(lambda request: httpx.Response(200, json=body)).read_sendtask("task-1")
    assert result["data"]["sendtask_create_ut"] == 100
    assert body["data"]["sendtask_create_ut"] == "100"


@pytest.mark.parametrize("value", [None, True, "", "bad", 0, -1, 1.5, float("inf"), {}, "1.5"])
def test_invalid_versions_are_rejected(value):
    with pytest.raises(TaskReadError):
        normalize_timestamp(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [None, {}, {"pause": False}, {"pause": False, "stop_time_new": -1, "summary": {}}])
async def test_incomplete_metadata_is_not_filled_with_defaults(metadata):
    body = task_body()
    body["metadata"] = metadata
    with pytest.raises(TaskReadError):
        await reader(lambda request: httpx.Response(200, json=body)).read_sendtask("task-1")


@pytest.mark.asyncio
async def test_second_page_failure_does_not_return_first_page():
    pages = []

    def handler(request):
        page = json.loads(request.content)["page_sn"]
        pages.append(page)
        if page == 2:
            return httpx.Response(500, json={"error": "failed"})
        return httpx.Response(200, json={"data": [{**task_body()["data"], "sendtask_uuid": str(index)} for index in range(20)]})

    with pytest.raises(TaskReadError):
        await reader(handler).read_sendtasks()
    assert pages == [1, 2]


@pytest.mark.asyncio
async def test_empty_lists_are_success_without_pretest_fallback():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    service = reader(handler)
    assert await service.read_sendtasks() == []
    assert await service.read_sendlog("task-1", sendlog_type="test") == []
    assert len(calls) == 2
    assert calls[-1]["sendlog_type"] == "test"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"data": None}, {"data": {}}, {"data": [None]}, {"data": [{"no_uuid": True}]},
    {"data": [], "metadata": {"total": 1}}, {"data": [], "metadata": {"total": "0"}},
])
async def test_malformed_or_incomplete_pages_fail(body):
    with pytest.raises(TaskReadError):
        await reader(lambda request: httpx.Response(200, json=body)).read_sendtasks()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_snapshot_checks_version_around_all_reads(changed):
    lookups = []

    def handler(request):
        if request.url.path.endswith("get_sendtask"):
            lookups.append(request)
            return httpx.Response(200, json=task_body(101 if changed and len(lookups) == 2 else 100))
        if request.url.path.endswith("get_testcase"):
            return httpx.Response(200, json={"data": {"testcase_uuid": "task-1"}})
        return httpx.Response(200, json={"data": []})

    if changed:
        with pytest.raises(TaskVersionChanged):
            await reader(handler).read_task_snapshot("task-1")
    else:
        snapshot = await reader(handler).read_task_snapshot("task-1")
        assert snapshot.create_ut == 100
        assert snapshot.sendlogs == []
        assert snapshot.sendlog_type == "test"
    assert len(lookups) == 2


@pytest.mark.asyncio
async def test_sendlog_second_page_error_never_falls_back():
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["page_sn"] == 2:
            return httpx.Response(403, json={"sub_code": 40300})
        return httpx.Response(200, json={"data": [sendlog_record(str(index)) for index in range(200)]})

    with pytest.raises(TaskReadError):
        await reader(handler).read_sendlog("task-1", sendlog_type="test")
    assert [call["page_sn"] for call in calls] == [1, 2]
    assert all(call["sendlog_type"] == "test" for call in calls)


@pytest.mark.asyncio
async def test_complete_multiple_pages_with_total_and_normalized_logs():
    def handler(request):
        page = json.loads(request.content)["page_sn"]
        records = [sendlog_record(str(index)) for index in range(200)] if page == 1 else [sendlog_record("last")]
        return httpx.Response(200, json={"data": records, "metadata": {"total": 201}})

    records = await reader(handler).read_sendlog("task-1", sendlog_type="pretest")
    assert len(records) == 201
    assert records[-1]["uuid"] == "last"
    assert records[0]["plan_time"] == 100
    assert records[0]["access_time"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["duplicate", "changed_total", "short_page"])
async def test_unstable_pages_are_rejected(case):
    def handler(request):
        page = json.loads(request.content)["page_sn"]
        records = [{**task_body()["data"], "sendtask_uuid": str(index)} for index in range(20)]
        if page == 1:
            return httpx.Response(200, json={"data": records, "metadata": {"total": 21}})
        last = records[:1] if case == "duplicate" else []
        return httpx.Response(200, json={"data": last, "metadata": {"total": 22 if case == "changed_total" else 21}})

    with pytest.raises(TaskReadError):
        await reader(handler).read_sendtasks()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("uuid", None), ("target_email", None), ("plan_time", "bad"),
    ("send_time", None), ("access_time", "not-an-array"), ("sendtask_uuid", "other-task"),
])
async def test_invalid_sendlog_fields_fail(field, value):
    record = {**sendlog_record(), field: value}
    with pytest.raises(TaskReadError):
        await reader(lambda request: httpx.Response(200, json={"data": [record]})).read_sendlog("task-1", sendlog_type="test")


@pytest.mark.asyncio
async def test_missing_event_field_is_not_silently_defaulted():
    record = sendlog_record()
    del record["access_time"]
    with pytest.raises(TaskReadError, match="incomplete_sendlog_events"):
        await reader(lambda request: httpx.Response(200, json={"data": [record]})).read_sendlog("task-1", sendlog_type="test")


@pytest.mark.asyncio
async def test_snapshot_uses_explicit_pretest_mode_and_keeps_all_events():
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        if request.url.path.endswith("get_sendtask"):
            body = task_body()
            body["data"]["pre_test_enable"] = True
            return httpx.Response(200, json=body)
        if request.url.path.endswith("get_testcase"):
            return httpx.Response(200, json={"data": {"testcase_uuid": "task-1"}})
        return httpx.Response(200, json={"data": [{**sendlog_record(), "access_time": [100, 101]}]})

    snapshot = await reader(handler).read_task_snapshot("task-1", sendlog_type="pretest")
    assert snapshot.sendlog_type == "pretest"
    assert snapshot.sendlogs[0]["access_time"] == [100, 101]
    assert all(payload["sendlog_type"] == "pretest" for path, payload in requests if not path.endswith("get_testcase"))


@pytest.mark.asyncio
@pytest.mark.parametrize("testcase", [None, [], {}, {"testcase_uuid": "other-task"}])
async def test_invalid_testcase_prevents_snapshot(testcase):
    def handler(request):
        if request.url.path.endswith("get_sendtask"):
            return httpx.Response(200, json=task_body())
        if request.url.path.endswith("get_testcase"):
            return httpx.Response(200, json={"data": testcase})
        return httpx.Response(200, json={"data": []})

    with pytest.raises(TaskReadError, match="invalid_testcase"):
        await reader(handler).read_task_snapshot("task-1")


@pytest.mark.asyncio
async def test_snapshot_fails_if_task_disappears_during_download():
    count = 0

    def handler(request):
        nonlocal count
        if request.url.path.endswith("get_sendtask"):
            count += 1
            if count == 2:
                return httpx.Response(404, json={"sub_code": 40400})
            return httpx.Response(200, json=task_body())
        if request.url.path.endswith("get_testcase"):
            return httpx.Response(200, json={"data": {"testcase_uuid": "task-1"}})
        return httpx.Response(200, json={"data": []})

    with pytest.raises(TaskVersionChanged, match="task_disappeared_during_read"):
        await reader(handler).read_task_snapshot("task-1")


def test_existing_client_factory_uses_current_settings_and_dynamic_headers():
    from unittest.mock import patch
    from backend.services.getSe2data import getSe2data

    client = getSe2data()
    service = client.get_task_reader()
    assert service.url == client.url.rstrip("/")
    assert service.verify == client.verify
    with patch("backend.services.getSe2data.get_token.get", side_effect=["first", "second"]):
        assert service.headers_factory()["cookie"] == "first"
        assert service.headers_factory()["cookie"] == "second"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("sendtask_uuid", "other-task"), ("sendtask_id", None),
    ("sendtask_owner_gid", "org-1"), ("pre_test_enable", "false"),
    ("sendtask_create_ut", None), ("sendtask_create_ut", "invalid"),
])
async def test_incomplete_task_cannot_become_snapshot(field, value):
    body = task_body()
    body["data"][field] = value
    with pytest.raises(TaskReadError):
        await reader(lambda request: httpx.Response(200, json=body)).read_task_snapshot("task-1")


@pytest.mark.asyncio
async def test_redirect_does_not_follow_login_page():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://login.test"}, json={"data": None})

    with pytest.raises(TaskReadError, match="http_error"):
        await reader(handler).read_sendtask("task-1")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_exact_page_size_requires_terminating_page():
    pages = []

    def handler(request):
        page = json.loads(request.content)["page_sn"]
        pages.append(page)
        records = [{**task_body()["data"], "sendtask_uuid": str(index)} for index in range(20)] if page == 1 else []
        return httpx.Response(200, json={"data": records, "metadata": {"total": 20}})

    assert len(await reader(handler).read_sendtasks()) == 20
    assert pages == [1, 2]