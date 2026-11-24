import pytest
from fastapi import HTTPException

from backend.services.structured_page import (
    mask_value,
    render_structured_page,
    stream_structured_generation_with_retries,
    StructuredOutputValidationError,
    validate_custom_field_updates,
    validate_page_spec,
    validate_structured_html,
)


def make_spec(field: dict) -> dict:
    return {
        "page_title": "資料填寫",
        "main_title": "聯絡資料",
        "description": "",
        "submit_text": "送出",
        "logo_mode": "none",
        "fields": [field],
    }


@pytest.mark.parametrize(
    ("mode", "keep_chars", "value", "expected"),
    [
        ("keep_end", 3, "123456789", "******789"),
        ("keep_end", 3, "123", "*23"),
        ("keep_end", 3, "12", "*2"),
        ("keep_end", 3, "1", "*"),
        ("keep_start", 5, "123456789", "12345****"),
        ("keep_start", 5, "12345", "1234*"),
        ("keep_start", 5, "中文", "中*"),
        ("full", None, "王小明", "***"),
        ("none", None, "public", "public"),
    ],
)
def test_mask_value_boundaries(mode, keep_chars, value, expected):
    field = {"type": "text", "mask_mode": mode, "keep_chars": keep_chars}
    assert mask_value(value, field) == expected

@pytest.mark.parametrize("field_type", ["national_id", "phone", "custom"])
def test_validate_spec_allows_unmasked_non_password_fields(field_type):
    field = {
        "id": "field_1",
        "label": "測試欄位",
        "type": field_type,
        "required": True,
        "mask_mode": "none",
        "custom_rule": "六位英數字" if field_type == "custom" else "",
        "validation_pattern": "[A-Za-z0-9]{6}" if field_type == "custom" else "",
    }

    spec = validate_page_spec(make_spec(field))

    assert spec["fields"][0]["mask_mode"] == "none"


def test_validate_spec_rejects_custom_field_for_non_ai_page():
    with pytest.raises(HTTPException, match="不支援指定內容欄位"):
        validate_page_spec(make_spec({
            "id": "employee_code",
            "label": "員工編號",
            "type": "custom",
            "required": True,
            "mask_mode": "full",
            "custom_rule": "六位數字",
        }), allow_custom=False)


def test_rendered_page_matches_structured_contract():
    spec = validate_page_spec(make_spec({
        "id": "contact_phone",
        "label": "手機",
        "type": "phone",
        "required": True,
        "mask_mode": "keep_end",
        "keep_chars": 3,
    }))
    html = render_structured_page(spec, template_type="modern")
    validate_structured_html(html, spec)
    assert 'pattern="09[0-9]{8}"' in html
    assert "recordingStructuredForm.js" in html
    assert "recordingLogin.js" not in html


def test_html_validation_rejects_field_order_change():
    spec = validate_page_spec({
        **make_spec({
            "id": "first",
            "label": "第一欄",
            "type": "text",
            "required": True,
            "mask_mode": "full",
        }),
        "fields": [
            {
                "id": "first",
                "label": "第一欄",
                "type": "text",
                "required": True,
                "mask_mode": "full",
            },
            {
                "id": "second",
                "label": "第二欄",
                "type": "email",
                "required": False,
                "mask_mode": "none",
            },
        ],
    })
    html = render_structured_page(spec)
    first = html.index('data-structured-field-id="first"')
    second = html.index('data-structured-field-id="second"')
    invalid_html = html[:first] + html[second:second + 34] + html[first + 33:second] + html[first:first + 33] + html[second + 34:]

    with pytest.raises(HTTPException, match="欄位數量、ID 或順序"):
        validate_structured_html(invalid_html, spec)


def test_html_validation_rejects_untracked_input():
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec).replace(
        '<div id="structured-fields">',
        '<div id="structured-fields"><input name="untracked">',
    )

    with pytest.raises(HTTPException, match="規格以外"):
        validate_structured_html(html, spec)


def test_html_validation_rejects_second_form():
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec).replace("</main>", "<form></form></main>")

    with pytest.raises(HTTPException, match="只能包含一個表單"):
        validate_structured_html(html, spec)


def test_saved_page_cannot_add_custom_field_without_ai():
    previous = make_spec({
        "id": "name",
        "label": "姓名",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    })
    updated = {
        **previous,
        "fields": [
            previous["fields"][0],
            {
                "id": "employee_code",
                "label": "員工代碼",
                "type": "custom",
                "required": True,
                "mask_mode": "full",
                "custom_rule": "六位數字",
                "validation_pattern": "[0-9]{6}",
            },
        ],
    }

    with pytest.raises(HTTPException, match="不可新增指定內容欄位"):
        validate_custom_field_updates(previous, updated)


def test_saved_custom_rule_is_immutable():
    previous = make_spec({
        "id": "employee_code",
        "label": "員工代碼",
        "type": "custom",
        "required": True,
        "mask_mode": "full",
        "custom_rule": "六位數字",
        "validation_pattern": "[0-9]{6}",
    })
    updated = {
        **previous,
        "fields": [{**previous["fields"][0], "validation_pattern": "[0-9]{8}"}],
    }

    with pytest.raises(HTTPException, match="特殊規則不可修改"):
        validate_custom_field_updates(previous, updated)


@pytest.mark.parametrize("extra_control", ["<textarea></textarea>", "<select></select>"])
def test_html_validation_rejects_extra_form_controls(extra_control):
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec).replace("</form>", f"{extra_control}</form>")

    with pytest.raises(HTTPException, match="規格以外的表單控制項"):
        validate_structured_html(html, spec)


def test_html_validation_rejects_inline_event_attributes():
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec).replace("<main ", '<main onclick="alert(1)" ')

    with pytest.raises(HTTPException, match="行內事件程式"):
        validate_structured_html(html, spec)


def test_rendered_fields_do_not_have_native_submission_names():
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec)

    assert 'name="contact"' not in html


def test_html_validation_rejects_changed_fixed_content():
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec).replace(
        '<h1 id="custom-main-title">聯絡資料</h1>',
        '<h1 id="custom-main-title">其他標題</h1>',
    )

    with pytest.raises(HTTPException, match="custom-main-title"):
        validate_structured_html(html, spec)


def test_html_validation_rejects_changed_field_label():
    spec = validate_page_spec(make_spec({
        "id": "contact",
        "label": "聯絡方式",
        "type": "text",
        "required": True,
        "mask_mode": "full",
    }))
    html = render_structured_page(spec).replace(
        '>聯絡方式<span class="structured-required"',
        '>其他名稱<span class="structured-required"',
    )

    with pytest.raises(HTTPException, match="欄位名稱"):
        validate_structured_html(html, spec)


@pytest.mark.asyncio
async def test_structured_generation_stops_after_first_valid_output():
    calls = []

    async def stream_factory(attempt):
        calls.append(attempt)

        async def stream():
            yield ("chunk", "valid")
            yield ("done", "valid-html")

        return stream()

    events = [event async for event in stream_structured_generation_with_retries(
        stream_factory,
        lambda html: {"html": html},
    )]

    assert calls == [1]
    assert events[-1] == ("done", {"html": "valid-html", "page_spec": {"html": "valid-html"}})


@pytest.mark.asyncio
async def test_structured_generation_succeeds_on_third_attempt():
    calls = []

    async def stream_factory(attempt):
        calls.append(attempt)

        async def stream():
            yield ("done", f"html-{attempt}")

        return stream()

    def validate_output(html):
        if html != "html-3":
            raise StructuredOutputValidationError(f"invalid {html}")
        return {"accepted": True}

    events = [event async for event in stream_structured_generation_with_retries(
        stream_factory,
        validate_output,
    )]

    assert calls == [1, 2, 3]
    assert [kind for kind, _ in events].count("validation_error") == 2
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_structured_generation_reports_error_after_three_invalid_outputs():
    calls = []

    async def stream_factory(attempt):
        calls.append(attempt)

        async def stream():
            yield ("done", f"html-{attempt}")

        return stream()

    with pytest.raises(StructuredOutputValidationError, match="連續 3 次"):
        _ = [event async for event in stream_structured_generation_with_retries(
            stream_factory,
            lambda _html: (_ for _ in ()).throw(StructuredOutputValidationError("invalid")),
        )]

    assert calls == [1, 2, 3]


@pytest.mark.asyncio
async def test_structured_generation_does_not_retry_provider_errors():
    calls = []

    async def stream_factory(attempt):
        calls.append(attempt)

        async def stream():
            raise RuntimeError("provider unavailable")
            yield

        return stream()

    with pytest.raises(RuntimeError, match="provider unavailable"):
        _ = [event async for event in stream_structured_generation_with_retries(
            stream_factory,
            lambda _html: {},
        )]

    assert calls == [1]