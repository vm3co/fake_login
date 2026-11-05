from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import httpx


class TaskReadError(RuntimeError):
    """A complete, validated result could not be obtained; never implies deletion."""

    def __init__(self, reason: str, *, http_status: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status


class TaskNotFound(TaskReadError):
    pass


class TaskVersionChanged(TaskReadError):
    pass


@dataclass(frozen=True)
class TaskSnapshot:
    task: dict
    metadata: dict
    sendlogs: list[dict]
    testcase: dict
    create_ut: int
    sendlog_type: str


def normalize_timestamp(value, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TaskReadError("invalid_timestamp")
    try:
        timestamp = int(value)
        if isinstance(value, float) and timestamp != value:
            raise ValueError
    except (ValueError, OverflowError):
        raise TaskReadError("invalid_timestamp") from None
    if timestamp < 0 or (timestamp == 0 and not allow_zero):
        raise TaskReadError("invalid_timestamp")
    return timestamp


class SE2TaskReader:
    """Read-only strict API for future sync callers; legacy readers stay unchanged."""

    def __init__(
        self,
        url: str,
        headers_factory: Callable[[], dict],
        verify,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.url = url.rstrip("/")
        self.headers_factory = headers_factory
        self.verify = verify
        self.transport = transport

    async def _post(self, endpoint: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=60.0, verify=self.verify, transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.url + endpoint, headers=self.headers_factory(), json=payload,
                )
        except httpx.RequestError:
            raise TaskReadError("transport_error") from None

        try:
            body = response.json()
        except (ValueError, UnicodeError):
            raise TaskReadError("invalid_json", http_status=response.status_code) from None
        if not isinstance(body, dict):
            raise TaskReadError("invalid_response", http_status=response.status_code)
        if (
            endpoint == "/api/case/get_sendtask"
            and payload.get("sendlog_type") == "test"
            and response.status_code == 404
            and type(body.get("sub_code")) is int
            and body["sub_code"] == 40400
        ):
            raise TaskNotFound("task_not_found", http_status=404)
        if not 200 <= response.status_code < 300:
            raise TaskReadError("http_error", http_status=response.status_code)
        if body.get("error") or body.get("sub_code") not in (None, 20000):
            raise TaskReadError("business_error", http_status=response.status_code)
        if "data" not in body:
            raise TaskReadError("missing_data", http_status=response.status_code)
        return body

    @staticmethod
    def _mode(sendlog_type: str):
        if sendlog_type not in {"test", "pretest"}:
            raise TaskReadError("invalid_sendlog_type")

    @staticmethod
    def _task_record(value, expected_uuid: str | None = None) -> dict:
        if not isinstance(value, dict):
            raise TaskReadError("invalid_task")
        record = deepcopy(value)
        if not isinstance(record.get("sendtask_uuid"), str) or not record["sendtask_uuid"]:
            raise TaskReadError("missing_task_uuid")
        if expected_uuid is not None and record["sendtask_uuid"] != expected_uuid:
            raise TaskReadError("task_uuid_mismatch")
        if not isinstance(record.get("sendtask_id"), str) or not record["sendtask_id"]:
            raise TaskReadError("missing_task_name")
        if not isinstance(record.get("sendtask_owner_gid"), list) or any(
            not isinstance(group, str) for group in record["sendtask_owner_gid"]
        ):
            raise TaskReadError("invalid_task_scope")
        if not isinstance(record.get("pre_test_enable"), bool):
            raise TaskReadError("invalid_pretest_flag")
        record["sendtask_create_ut"] = normalize_timestamp(record.get("sendtask_create_ut"))
        return record

    @staticmethod
    def _metadata(value) -> dict:
        if not isinstance(value, dict) or not isinstance(value.get("summary"), dict):
            raise TaskReadError("incomplete_metadata")
        if not isinstance(value.get("pause"), bool):
            raise TaskReadError("invalid_pause")
        stop_time = value.get("stop_time_new")
        if not (type(stop_time) is int and stop_time == -1) and stop_time != "-1":
            normalize_timestamp(stop_time, allow_zero=True)
        person_count = value["summary"].get("person_count")
        if type(person_count) is not int or person_count < 0:
            raise TaskReadError("invalid_person_count")
        return deepcopy(value)

    async def read_sendtask(self, task_uuid: str, *, sendlog_type: str = "test") -> dict:
        self._mode(sendlog_type)
        body = await self._post("/api/case/get_sendtask", {
            "sendtask_uuid": task_uuid, "sendlog_type": sendlog_type,
        })
        return {
            "data": self._task_record(body["data"], task_uuid),
            "metadata": self._metadata(body.get("metadata")),
        }

    async def _pages(self, endpoint: str, payload: dict, identity: str) -> list[dict]:
        records = []
        seen = set()
        expected_total = None
        for page in range(1, 10001):
            body = await self._post(endpoint, {**payload, "page_sn": page})
            page_data = body["data"]
            if not isinstance(page_data, list) or len(page_data) > payload["record_page"]:
                raise TaskReadError("invalid_page")
            metadata = body.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                raise TaskReadError("invalid_page_metadata")
            if metadata is not None and "total" in metadata:
                total = metadata["total"]
                if type(total) is not int or total < 0:
                    raise TaskReadError("invalid_total")
                if expected_total is not None and expected_total != total:
                    raise TaskReadError("total_changed")
                expected_total = total
            for record in page_data:
                if not isinstance(record, dict) or not isinstance(record.get(identity), str) or not record[identity]:
                    raise TaskReadError("invalid_page_record")
                if record[identity] in seen:
                    raise TaskReadError("duplicate_page_record")
                seen.add(record[identity])
                records.append(record)
            if expected_total is not None and len(records) > expected_total:
                raise TaskReadError("total_mismatch")
            if len(page_data) < payload["record_page"]:
                if expected_total is not None and len(records) != expected_total:
                    raise TaskReadError("incomplete_pages")
                return records
        raise TaskReadError("page_limit_exceeded")

    async def read_sendtasks(self, *, start_time=None, end_time=None, keyword=None) -> list[dict]:
        records = await self._pages("/api/case/get_sendtasks", {
            "start_time": start_time, "end_time": end_time,
            "filter_time_range": 0 if start_time is None and end_time is None else 99,
            "order_field": "CreateTime", "order_method": "desc", "record_page": 20,
            "sendtask_keyword": keyword or "", "sendtask_prestart": "no", "time_field": "CreateTime",
        }, "sendtask_uuid")
        return [self._task_record(record) for record in records]

    async def read_sendlog(self, task_uuid: str, *, sendlog_type: str) -> list[dict]:
        self._mode(sendlog_type)
        records = await self._pages("/api/case/get_sendlog", {
            "sendtask_uuid": task_uuid, "sendlog_type": sendlog_type,
            "record_page": 200, "search_keyword": "", "behavior_filter": 0,
            "etime": None, "stime": None, "order_method": "asc",
            "search_order_by": "B", "search_send_result": "ALL",
        }, "uuid")
        result = []
        for value in records:
            record = deepcopy(value)
            if record.get("sendtask_uuid", task_uuid) != task_uuid:
                raise TaskReadError("sendlog_task_mismatch")
            for field in ("target_email", "person_info", "template_uuid", "send_res"):
                if field not in record or not isinstance(record[field], str):
                    raise TaskReadError("incomplete_sendlog")
            for field in ("plan_time", "send_time"):
                record[field] = normalize_timestamp(record.get(field), allow_zero=True)
            for field in (
                "access_time", "access_src", "access_dev", "click_time", "click_src",
                "click_dev", "file_time", "file_src", "file_dev",
            ):
                if field not in record or (record[field] is not None and not isinstance(record[field], list)):
                    raise TaskReadError("incomplete_sendlog_events")
            result.append(record)
        return result

    async def read_task_snapshot(self, task_uuid: str, *, sendlog_type: str = "test") -> TaskSnapshot:
        before = await self.read_sendtask(task_uuid, sendlog_type=sendlog_type)
        actual_mode = "pretest" if before["data"]["pre_test_enable"] else "test"
        sendlogs = await self.read_sendlog(task_uuid, sendlog_type=actual_mode)
        testcase_body = await self._post("/api/case/get_testcase", {"testcase_uuid": task_uuid})
        testcase = testcase_body["data"]
        if not isinstance(testcase, dict) or testcase.get("testcase_uuid") != task_uuid:
            raise TaskReadError("invalid_testcase")
        try:
            after = await self.read_sendtask(task_uuid, sendlog_type=sendlog_type)
        except TaskNotFound:
            raise TaskVersionChanged("task_disappeared_during_read") from None
        if (
            before["data"]["sendtask_create_ut"] != after["data"]["sendtask_create_ut"]
            or before["data"]["pre_test_enable"] != after["data"]["pre_test_enable"]
        ):
            raise TaskVersionChanged("task_version_changed")
        return TaskSnapshot(
            task=before["data"], metadata=before["metadata"], sendlogs=sendlogs,
            testcase=deepcopy(testcase), create_ut=before["data"]["sendtask_create_ut"],
            sendlog_type=actual_mode,
        )