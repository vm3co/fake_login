import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.structured_page import render_structured_page, validate_page_spec


SPEC = {
    "page_title": "資料填寫",
    "main_title": "聯絡資料",
    "description": "請填寫測試資料",
    "submit_text": "送出",
    "logo_mode": "none",
    "fields": [
        {
            "id": "phone",
            "label": "手機",
            "type": "phone",
            "required": True,
            "mask_mode": "keep_end",
            "keep_chars": 3,
            "custom_rule": "",
            "validation_pattern": "",
        }
    ],
}


@pytest.fixture
def structured_user():
    from backend.api.user_api import get_current_user
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "acct_uuid": "owner-1",
        "user_type": "user",
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_structured_page_saves_spec_and_html(async_client, structured_user, monkeypatch, tmp_path):
    create = AsyncMock()
    get_one = AsyncMock(return_value=None)
    monkeypatch.setattr("backend.api.trigger_page_api.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("backend.api.trigger_page_api.db_controller.get_one", get_one)
    monkeypatch.setattr("backend.api.trigger_page_api.db_controller.create", create)

    response = await async_client.post("/api/trigger_page/structured/create", data={
        "pageLabel": "測試表單",
        "pageValue": "structured_test",
        "pageSpec": json.dumps(SPEC),
        "source": "custom",
        "templateType": "classic",
        "bgColor": "#edf2ef",
        "allowedDomainId": "",
    })

    assert response.status_code == 200
    created_data = create.await_args.args[1]
    assert created_data["page_spec"]["fields"][0]["mask_mode"] == "keep_end"
    assert created_data["spec_revision"] == 1
    html = (tmp_path / "structured_test.html").read_text(encoding="utf-8")
    assert "recordingStructuredForm.js" in html
    assert "recordingLogin.js" not in html


@pytest.mark.asyncio
async def test_update_structured_page_rejects_stale_revision(async_client, structured_user, monkeypatch, tmp_path):
    normalized_spec = validate_page_spec(SPEC)
    page = SimpleNamespace(
        id=1,
        page_value="structured_test",
        page_label="測試表單",
        page_spec=normalized_spec,
        spec_revision=2,
        owner_uuid="owner-1",
    )
    get_one = AsyncMock(return_value=page)
    update = AsyncMock()
    monkeypatch.setattr("backend.api.trigger_page_api.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("backend.api.trigger_page_api.db_controller.get_one", get_one)
    monkeypatch.setattr("backend.api.trigger_page_api.db_controller.update", update)
    original_html = render_structured_page(normalized_spec, revision=2)
    (tmp_path / "structured_test.html").write_text(original_html, encoding="utf-8")

    response = await async_client.post(
        "/api/trigger_page/structured/update",
        data={
            "pageLabel": "測試表單",
            "pageValue": "structured_test",
            "oldPageValue": "structured_test",
            "pageSpec": json.dumps(normalized_spec),
            "specRevision": "1",
            "allowedDomainId": "",
        },
        files={"file": ("structured_test.html", original_html, "text/html")},
    )

    assert response.status_code == 409
    update.assert_not_awaited()
    assert (tmp_path / "structured_test.html").read_text(encoding="utf-8") == original_html


@pytest.mark.asyncio
async def test_legacy_update_rejects_structured_page(async_client, structured_user, monkeypatch):
    page = SimpleNamespace(
        id=1,
        page_value="structured_test",
        page_spec=validate_page_spec(SPEC),
        owner_uuid="owner-1",
    )
    monkeypatch.setattr(
        "backend.api.trigger_page_api.db_controller.get_one",
        AsyncMock(return_value=page),
    )

    response = await async_client.post("/api/trigger_page/update", data={
        "pageLabel": "測試表單",
        "pageValue": "structured_test",
        "oldPageValue": "structured_test",
        "allowedDomainId": "",
    })

    assert response.status_code == 409
    assert "欄位編輯器" in response.json()["detail"]