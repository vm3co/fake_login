import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI


design_generator_stub = ModuleType("backend.services.design_generator")
design_generator_stub.get_design_context = AsyncMock(return_value={})
sys.modules.setdefault("backend.services.design_generator", design_generator_stub)
os.environ.setdefault("APP_BASE_DIR", "/tmp/fake_login_structured_api_tests")

from backend.api import trigger_page_api
from backend.api.user_api import get_current_user


def make_spec() -> dict:
    return {
        "page_title": "資料填寫",
        "main_title": "聯絡資料",
        "description": "請填寫以下資料",
        "submit_text": "送出",
        "logo_mode": "none",
        "fields": [{
            "id": "phone",
            "label": "手機",
            "type": "phone",
            "required": True,
            "mask_mode": "keep_end",
            "keep_chars": 3,
            "custom_rule": "",
            "validation_pattern": "",
        }],
    }


@pytest.fixture
async def structured_client(tmp_path, monkeypatch):
    monkeypatch.setattr(trigger_page_api, "UPLOAD_DIR", tmp_path)
    app = FastAPI()
    app.include_router(trigger_page_api.get_router(SimpleNamespace()), prefix="/api/trigger_page")
    app.dependency_overrides[get_current_user] = lambda: {
        "acct_uuid": "owner-1",
        "user_type": "user",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        client.structured_test_app = app
        yield client, tmp_path


@pytest.mark.asyncio
async def test_create_structured_custom_page_persists_spec(structured_client, monkeypatch):
    client, upload_dir = structured_client
    create = AsyncMock()
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=None))
    monkeypatch.setattr(trigger_page_api.db_controller, "create", create)

    response = await client.post("/api/trigger_page/structured/create", data={
        "pageLabel": "聯絡表單",
        "pageValue": "contact_form",
        "pageSpec": json.dumps(make_spec()),
        "source": "custom",
        "templateType": "modern",
        "allowedDomainId": "",
    })

    assert response.status_code == 200, response.text
    saved_html = (upload_dir / "contact_form.html").read_text(encoding="utf-8")
    assert "recordingStructuredForm.js" in saved_html
    assert "recordingLogin.js" not in saved_html
    payload = create.await_args.args[1]
    assert payload["page_spec"]["fields"][0]["mask_mode"] == "keep_end"
    assert payload["spec_revision"] == 1


@pytest.mark.asyncio
async def test_structured_detail_allows_copy_but_not_edit_for_non_owner(structured_client, monkeypatch):
    client, _ = structured_client
    page = SimpleNamespace(
        page_label="他人頁面",
        page_value="other_page",
        allowed_domain_id=None,
        page_spec=make_spec(),
        spec_revision=3,
        owner_uuid="owner-2",
    )
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=page))

    edit_response = await client.get("/api/trigger_page/structured/detail", params={
        "pageValue": "other_page",
        "intent": "edit",
    })
    copy_response = await client.get("/api/trigger_page/structured/detail", params={
        "pageValue": "other_page",
        "intent": "copy",
    })

    assert edit_response.status_code == 403
    assert copy_response.status_code == 200
    assert copy_response.json()["specRevision"] == 3


@pytest.mark.asyncio
async def test_structured_update_rejects_stale_revision_before_writing(structured_client, monkeypatch):
    client, upload_dir = structured_client
    page = SimpleNamespace(
        id=10,
        page_spec=make_spec(),
        spec_revision=2,
        owner_uuid="owner-1",
    )
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=page))
    monkeypatch.setattr(trigger_page_api.db_controller, "update", AsyncMock())

    response = await client.post(
        "/api/trigger_page/structured/update",
        data={
            "pageLabel": "聯絡表單",
            "pageValue": "contact_form",
            "oldPageValue": "contact_form",
            "pageSpec": json.dumps(make_spec()),
            "specRevision": "1",
            "allowedDomainId": "",
        },
        files={"file": ("contact_form.html", b"invalid", "text/html")},
    )

    assert response.status_code == 409
    assert not list(Path(upload_dir).glob("*.html"))
    assert not list(Path(upload_dir).glob("*.tmp"))
    assert not list(Path(upload_dir).glob("*.bak"))
    trigger_page_api.db_controller.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_update_rejects_structured_page(structured_client, monkeypatch):
    client, _ = structured_client
    page = SimpleNamespace(
        id=10,
        page_spec=make_spec(),
        owner_uuid="owner-1",
    )
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=page))

    response = await client.post("/api/trigger_page/update", data={
        "pageLabel": "聯絡表單",
        "pageValue": "contact_form",
        "oldPageValue": "contact_form",
        "allowedDomainId": "",
    })

    assert response.status_code == 409
    assert response.json()["detail"] == "結構化頁面請使用欄位編輯器修改"


@pytest.mark.asyncio
async def test_structured_copy_requires_source_page(structured_client, monkeypatch):
    client, _ = structured_client
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=None))

    response = await client.post(
        "/api/trigger_page/structured/create",
        data={
            "pageLabel": "副本",
            "pageValue": "contact_copy",
            "pageSpec": json.dumps(make_spec()),
            "source": "copy",
            "allowedDomainId": "",
        },
        files={"file": ("contact_copy.html", b"invalid", "text/html")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "複製頁面缺少有效的來源網址 ID"


@pytest.mark.asyncio
async def test_create_structured_page_generates_page_value_when_blank(structured_client, monkeypatch):
    client, upload_dir = structured_client
    create = AsyncMock()
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=None))
    monkeypatch.setattr(trigger_page_api.db_controller, "create", create)

    response = await client.post("/api/trigger_page/structured/create", data={
        "pageLabel": "自動網址",
        "pageValue": "",
        "pageSpec": json.dumps(make_spec()),
        "source": "custom",
        "allowedDomainId": "",
    })

    assert response.status_code == 200, response.text
    generated = response.json()["pageValue"]
    assert generated.startswith("page_")
    assert (upload_dir / f"{generated}.html").exists()
    assert create.await_args.args[1]["page_value"] == generated


@pytest.mark.asyncio
async def test_create_structured_page_rejects_duplicate_requested_value(structured_client, monkeypatch):
    client, _ = structured_client
    duplicate = SimpleNamespace(page_value="contact_form")
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=duplicate))

    response = await client.post("/api/trigger_page/structured/create", data={
        "pageLabel": "重複頁面",
        "pageValue": "contact_form",
        "pageSpec": json.dumps(make_spec()),
        "source": "custom",
        "allowedDomainId": "",
    })

    assert response.status_code == 409
    assert response.json()["detail"] == "網址 ID 'contact_form' 已存在"


@pytest.mark.asyncio
async def test_page_value_availability_handles_current_and_conflicting_pages(structured_client, monkeypatch):
    client, _ = structured_client
    current_page = SimpleNamespace(page_value="current_page", owner_uuid="owner-1")
    conflict_page = SimpleNamespace(page_value="used_page", owner_uuid="owner-2")

    async def get_one(_model, filters):
        return {
            "current_page": current_page,
            "used_page": conflict_page,
        }.get(filters.get("page_value"))

    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(side_effect=get_one))

    current_response = await client.get("/api/trigger_page/structured/page-value-availability", params={
        "pageValue": "current_page",
        "currentPageValue": "current_page",
    })
    conflict_response = await client.get("/api/trigger_page/structured/page-value-availability", params={
        "pageValue": "used_page",
        "currentPageValue": "current_page",
    })
    free_response = await client.get("/api/trigger_page/structured/page-value-availability", params={
        "pageValue": "free_page",
        "currentPageValue": "current_page",
    })

    assert current_response.json()["available"] is True
    assert conflict_response.json()["available"] is False
    assert free_response.json()["available"] is True


def _disable_ai_log_writes(monkeypatch):
    monkeypatch.setattr(trigger_page_api.ai_log, "new_generation_id", lambda: "test_generation")
    monkeypatch.setattr(trigger_page_api.ai_log, "write_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trigger_page_api.ai_log, "write_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trigger_page_api.ai_log, "write_timing", lambda *_args, **_kwargs: None)


@pytest.mark.asyncio
async def test_structured_ai_stream_succeeds_on_third_valid_output(structured_client, monkeypatch):
    client, _ = structured_client
    _disable_ai_log_writes(monkeypatch)
    normalized_spec = trigger_page_api.validate_page_spec(make_spec())
    valid_html = trigger_page_api.render_structured_page(normalized_spec, revision=1)
    attempts = []

    def fake_llm_caller(**_kwargs):
        attempt = len(attempts) + 1
        attempts.append(attempt)

        async def stream():
            yield ("done", valid_html if attempt == 3 else "<html>invalid</html>")

        return stream()

    client.structured_test_app.state.trigger_page_llm_caller = fake_llm_caller
    response = await client.post("/api/trigger_page/generate_with_ai_stream", data={
        "prompt": "專業表單",
        "aiModel": "litellm",
        "useDesign": "false",
        "pageSpec": json.dumps(make_spec()),
        "pageValue": "",
    })

    assert response.status_code == 200
    assert attempts == [1, 2, 3]
    assert response.text.count('"type": "complete"') == 1
    assert response.text.count('"will_retry": true') == 2
    assert '"type": "error"' not in response.text


@pytest.mark.asyncio
async def test_structured_ai_stream_returns_one_error_after_three_invalid_outputs(structured_client, monkeypatch):
    client, _ = structured_client
    _disable_ai_log_writes(monkeypatch)
    attempts = []

    def fake_llm_caller(**_kwargs):
        attempts.append(len(attempts) + 1)

        async def stream():
            yield ("done", "<html>invalid</html>")

        return stream()

    client.structured_test_app.state.trigger_page_llm_caller = fake_llm_caller
    response = await client.post("/api/trigger_page/generate_with_ai_stream", data={
        "prompt": "專業表單",
        "aiModel": "litellm",
        "useDesign": "false",
        "pageSpec": json.dumps(make_spec()),
        "pageValue": "",
    })

    assert response.status_code == 200
    assert attempts == [1, 2, 3]
    assert response.text.count('"type": "complete"') == 0
    assert response.text.count('"type": "error"') == 1
    events = [
        json.loads(block.removeprefix("data: "))
        for block in response.text.strip().split("\n\n")
        if block.startswith("data: ")
    ]
    error_event = next(event for event in events if event["type"] == "error")
    assert "連續 3 次" in error_event["data"]["message"]


@pytest.mark.asyncio
async def test_structured_ai_rejects_duplicate_page_value_before_model_call(structured_client, monkeypatch):
    client, _ = structured_client
    duplicate = SimpleNamespace(page_value="used_page")
    monkeypatch.setattr(trigger_page_api.db_controller, "get_one", AsyncMock(return_value=duplicate))
    llm_caller = AsyncMock()
    client.structured_test_app.state.trigger_page_llm_caller = llm_caller

    response = await client.post("/api/trigger_page/generate_with_ai_stream", data={
        "prompt": "專業表單",
        "aiModel": "litellm",
        "useDesign": "false",
        "pageSpec": json.dumps(make_spec()),
        "pageValue": "used_page",
    })

    assert response.status_code == 409
    assert response.json()["detail"] == "網址 ID 'used_page' 已存在"
    llm_caller.assert_not_awaited()