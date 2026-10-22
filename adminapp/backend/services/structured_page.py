import re
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException


FIELD_TYPES = {"text", "email", "password", "national_id", "phone", "custom"}
MASK_MODES = {"none", "full", "keep_start", "keep_end"}
MAX_FIELDS = 10
MAX_KEEP_CHARS = 100
PAGE_SPEC_VERSION = 1
STRUCTURED_SCRIPT_NAME = "recordingStructuredForm.js"
STRUCTURED_SCRIPT_SOURCE = "{{ url_for('static', path='js/recordingStructuredForm.js') }}"


class StructuredOutputValidationError(ValueError):
    pass


async def stream_structured_generation_with_retries(
    stream_factory: Callable[[int], Awaitable[AsyncIterator[tuple[str, str]]]],
    validate_output: Callable[[str], dict],
    *,
    max_attempts: int = 3,
) -> AsyncIterator[tuple[str, Any]]:
    last_error = None
    for attempt in range(1, max_attempts + 1):
        yield ("attempt", {"attempt": attempt, "max_attempts": max_attempts})
        html_content = ""
        stream = await stream_factory(attempt)
        async for kind, payload in stream:
            if kind == "chunk":
                yield ("chunk", payload)
            elif kind == "done":
                html_content = payload

        try:
            completed_spec = validate_output(html_content)
        except StructuredOutputValidationError as exc:
            last_error = exc
            yield ("validation_error", {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "message": str(exc),
                "will_retry": attempt < max_attempts,
            })
            if attempt < max_attempts:
                continue
            break

        yield ("done", {"html": html_content, "page_spec": completed_spec})
        return

    raise StructuredOutputValidationError(
        f"AI 連續 {max_attempts} 次生成結果均未通過頁面結構驗證：{last_error}"
    )


def _validation_error(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def validate_page_spec(raw_spec: Any, *, allow_custom: bool = True) -> dict:
    if not isinstance(raw_spec, dict):
        raise _validation_error("頁面規格格式不正確")

    fields = raw_spec.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
        raise _validation_error(f"欄位數量必須介於 1 到 {MAX_FIELDS} 個")

    normalized = {
        "version": PAGE_SPEC_VERSION,
        "page_title": str(raw_spec.get("page_title", "")).strip(),
        "main_title": str(raw_spec.get("main_title", "")).strip(),
        "description": str(raw_spec.get("description", "")).strip(),
        "submit_text": str(raw_spec.get("submit_text", "送出")).strip(),
        "logo_mode": str(raw_spec.get("logo_mode", "ai")),
        "fields": [],
    }
    if not normalized["page_title"] or not normalized["main_title"]:
        raise _validation_error("分頁標題與網頁標題為必填")
    if not normalized["submit_text"]:
        raise _validation_error("提交按鈕文字為必填")
    if normalized["logo_mode"] not in {"ai", "none", "upload"}:
        raise _validation_error("Logo 模式不正確")

    field_ids = set()
    for index, raw_field in enumerate(fields, start=1):
        if not isinstance(raw_field, dict):
            raise _validation_error(f"第 {index} 個欄位格式不正確")

        field_id = str(raw_field.get("id", "")).strip()
        label = str(raw_field.get("label", "")).strip()
        field_type = str(raw_field.get("type", "text"))
        required = bool(raw_field.get("required", True))
        mask_mode = str(raw_field.get("mask_mode", "full"))
        custom_rule = str(raw_field.get("custom_rule", "")).strip()
        validation_pattern = str(raw_field.get("validation_pattern", "")).strip()

        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", field_id):
            raise _validation_error(f"第 {index} 個欄位 ID 不正確")
        if field_id in field_ids:
            raise _validation_error(f"欄位 ID '{field_id}' 重複")
        if not label:
            raise _validation_error(f"第 {index} 個欄位名稱為必填")
        if field_type not in FIELD_TYPES:
            raise _validation_error(f"第 {index} 個欄位類型不正確")
        if field_type == "custom" and not allow_custom:
            raise _validation_error("新增自訂頁面不支援指定內容欄位")
        if field_type == "custom" and not custom_rule:
            raise _validation_error(f"第 {index} 個指定內容欄位必須提供規格")
        if len(custom_rule) > 500 or len(validation_pattern) > 500:
            raise _validation_error(f"第 {index} 個欄位規格過長")

        if mask_mode not in MASK_MODES:
            raise _validation_error(f"第 {index} 個欄位遮罩模式不正確")
        if mask_mode in {"keep_start", "keep_end"}:
            try:
                keep_chars = int(raw_field.get("keep_chars"))
            except (TypeError, ValueError):
                raise _validation_error(f"第 {index} 個欄位保留碼數必須為整數")
            if not 1 <= keep_chars <= MAX_KEEP_CHARS:
                raise _validation_error(
                    f"第 {index} 個欄位保留碼數必須介於 1 到 {MAX_KEEP_CHARS}"
                )
        else:
            keep_chars = None

        field_ids.add(field_id)
        normalized["fields"].append({
            "id": field_id,
            "label": label,
            "type": field_type,
            "required": required,
            "mask_mode": mask_mode,
            "keep_chars": keep_chars,
            "custom_rule": custom_rule if field_type == "custom" else "",
            "validation_pattern": validation_pattern if field_type == "custom" else "",
        })

    return normalized


def mask_value(value: str, field: dict) -> str:
    value = "" if value is None else str(value)
    field_type = field.get("type")
    mode = field.get("mask_mode", "full")

    if not value or mode == "none":
        return value
    if mode == "full" or len(value) == 1:
        return "*" * len(value)

    keep_chars = int(field.get("keep_chars") or 1)
    visible_count = keep_chars if len(value) > keep_chars else len(value) - 1
    hidden_count = len(value) - visible_count
    if mode == "keep_start":
        return value[:visible_count] + ("*" * hidden_count)
    if mode == "keep_end":
        return ("*" * hidden_count) + value[-visible_count:]
    raise ValueError(f"Unsupported mask mode: {mode}")


def clone_page_spec(spec: dict) -> dict:
    return deepcopy(spec)


def validate_custom_field_updates(previous_spec: dict, next_spec: dict) -> None:
    previous_custom = {
        field["id"]: field
        for field in previous_spec.get("fields", [])
        if field.get("type") == "custom"
    }
    for field in next_spec.get("fields", []):
        if field.get("type") != "custom":
            continue
        previous = previous_custom.get(field["id"])
        if previous is None:
            raise _validation_error("儲存後不可新增指定內容欄位")
        if (
            field.get("custom_rule") != previous.get("custom_rule")
            or field.get("validation_pattern") != previous.get("validation_pattern")
        ):
            raise _validation_error(f"指定內容欄位 '{field['label']}' 的特殊規則不可修改")


def _input_attributes(field: dict) -> dict[str, str | None]:
    field_type = field["type"]
    attributes: dict[str, str | None] = {
        "id": f"structured-input-{field['id']}",
        "type": {
            "email": "email",
            "password": "password",
            "phone": "tel",
        }.get(field_type, "text"),
        "data-structured-field-id": field["id"],
        "data-field-type": field_type,
        "data-mask-mode": field["mask_mode"],
        "data-keep-chars": str(field["keep_chars"]) if field["keep_chars"] else None,
        "autocomplete": "off",
        "required": "required" if field["required"] else None,
    }
    if field_type == "national_id":
        attributes.update({
            "pattern": "[A-Za-z][12][0-9]{8}",
            "maxlength": "10",
            "inputmode": "text",
            "title": "請輸入英文字母、1 或 2，再接 8 個數字",
        })
    elif field_type == "phone":
        attributes.update({
            "pattern": "09[0-9]{8}",
            "maxlength": "10",
            "inputmode": "numeric",
            "title": "請輸入 09 開頭的 10 位數手機號碼",
        })
    elif field_type == "custom" and field.get("validation_pattern"):
        attributes["pattern"] = field["validation_pattern"]
        attributes["title"] = field["custom_rule"]
    return attributes


def build_field_html(field: dict) -> str:
    attributes = _input_attributes(field)
    attribute_text = " ".join(
        f'{name}="{escape(value, quote=True)}"'
        for name, value in attributes.items()
        if value is not None
    )
    required_mark = '<span class="structured-required" aria-hidden="true">*</span>' if field["required"] else ""
    return (
        f'<div class="structured-field" data-structured-field-row="{escape(field["id"], quote=True)}">'
        f'<label for="structured-input-{escape(field["id"], quote=True)}">'
        f'{escape(field["label"])}{required_mark}</label>'
        f'<input {attribute_text}>'
        "</div>"
    )


def build_fields_html(spec: dict) -> str:
    return "\n".join(build_field_html(field) for field in spec["fields"])


def render_structured_page(
    spec: dict,
    *,
    revision: int = 1,
    template_type: str = "classic",
    background_color: str = "#f2f2f2",
    background_image: str = "",
    logo_html: str = "",
) -> str:
    card_class = "structured-card structured-card-modern" if template_type == "modern" else "structured-card"
    background_image_css = f"url('{escape(background_image, quote=True)}')" if background_image else "none"
    description_html = escape(spec["description"])
    fields_html = build_fields_html(spec)
    return f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(spec["page_title"])}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            padding: 32px 18px;
            display: grid;
            place-items: center;
            color: #17212b;
            font-family: Georgia, "Times New Roman", serif;
            background-color: {escape(background_color)};
            background-image: {background_image_css};
            background-size: cover;
            background-position: center;
        }}
        .structured-card {{
            width: min(100%, 480px);
            padding: 34px;
            border: 1px solid #c8d0d8;
            border-top: 5px solid #0b6b5c;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.97);
            box-shadow: 0 18px 50px rgba(23, 33, 43, 0.15);
        }}
        .structured-card-modern {{ border-top-color: #d95532; }}
        #custom-brand-logo img {{ display: block; max-width: 180px; max-height: 80px; margin: 0 auto 22px; }}
        #custom-main-title {{ margin: 0; font-size: 2rem; line-height: 1.2; text-align: center; }}
        #structured-description {{ margin: 12px 0 26px; color: #586574; line-height: 1.6; text-align: center; }}
        #structured-description:empty {{ display: none; }}
        .structured-field {{ margin-bottom: 18px; }}
        .structured-field label {{ display: block; margin-bottom: 7px; font-size: 0.92rem; font-weight: 700; }}
        .structured-required {{ margin-left: 4px; color: #b42318; }}
        .structured-field input {{
            width: 100%;
            min-height: 44px;
            padding: 10px 12px;
            border: 1px solid #9da9b5;
            border-radius: 4px;
            background: #fff;
            color: #17212b;
            font: inherit;
        }}
        .structured-field input:focus {{ outline: 3px solid rgba(11, 107, 92, 0.2); border-color: #0b6b5c; }}
        #structured-submit {{
            width: 100%;
            min-height: 46px;
            border: 0;
            border-radius: 4px;
            background: #0b6b5c;
            color: #fff;
            font: 700 1rem Georgia, "Times New Roman", serif;
            cursor: pointer;
        }}
        @media (max-width: 560px) {{
            body {{ padding: 18px 12px; place-items: start center; }}
            .structured-card {{ padding: 25px 20px; }}
            #custom-main-title {{ font-size: 1.65rem; }}
        }}
    </style>
</head>
<body>
    <main class="{card_class}">
        <div id="custom-brand-logo">{logo_html}</div>
        <h1 id="custom-main-title">{escape(spec["main_title"])}</h1>
        <p id="structured-description">{description_html}</p>
        <form id="structured-form" data-spec-revision="{revision}">
            <div id="structured-fields">
                {fields_html}
            </div>
            <button id="structured-submit" type="submit">{escape(spec["submit_text"])}</button>
        </form>
    </main>
    <script>const API_BASE_PATH = "{{{{ api_base_path }}}}";</script>
    <script src="{{{{ url_for('static', path='js/{STRUCTURED_SCRIPT_NAME}') }}}}"></script>
</body>
</html>'''


class _StructuredHtmlInspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.id_counts = {}
        self.field_ids = []
        self.field_attributes = []
        self.script_sources = []
        self.inline_script_count = 0
        self.form_revision = None
        self.form_count = 0
        self.input_count = 0
        self.extra_form_control_count = 0
        self.event_attribute_count = 0
        self.current_capture = None
        self.captured_text = {}
        self.inline_scripts = []
        self._inline_script_parts = None
        self._field_label_parts = None
        self.field_labels = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
            self.id_counts[attributes["id"]] = self.id_counts.get(attributes["id"], 0) + 1
        if tag == "form":
            self.form_count += 1
        if tag == "input":
            self.input_count += 1
        if tag in {"textarea", "select"}:
            self.extra_form_control_count += 1
        self.event_attribute_count += sum(
            1 for name in attributes if name.lower().startswith("on")
        )
        field_id = attributes.get("data-structured-field-id")
        if tag == "input" and field_id:
            self.field_ids.append(field_id)
            self.field_attributes.append(attributes)
        if tag == "form" and attributes.get("id") == "structured-form":
            self.form_revision = attributes.get("data-spec-revision")
        if tag == "script":
            if attributes.get("src"):
                self.script_sources.append(attributes["src"])
            else:
                self.inline_script_count += 1
                self._inline_script_parts = []
        node_id = attributes.get("id")
        if tag == "title":
            self.current_capture = "title"
            self.captured_text["title"] = []
        elif node_id in {"custom-main-title", "structured-description", "structured-submit"}:
            self.current_capture = node_id
            self.captured_text[node_id] = []
        if tag == "label" and str(attributes.get("for") or "").startswith("structured-input-"):
            self._field_label_parts = []

    def handle_endtag(self, tag: str):
        if tag == "script" and self._inline_script_parts is not None:
            self.inline_scripts.append("".join(self._inline_script_parts).strip())
            self._inline_script_parts = None
        if tag == "label" and self._field_label_parts is not None:
            self.field_labels.append("".join(self._field_label_parts).rstrip("*").strip())
            self._field_label_parts = None
        if tag == "title" and self.current_capture == "title":
            self.current_capture = None
        elif tag in {"h1", "p", "button"} and self.current_capture:
            self.current_capture = None

    def handle_data(self, data: str):
        if self._inline_script_parts is not None:
            self._inline_script_parts.append(data)
        if self._field_label_parts is not None:
            self._field_label_parts.append(data)
        if self.current_capture:
            self.captured_text[self.current_capture].append(data)

    def text(self, key: str) -> str:
        return "".join(self.captured_text.get(key, [])).strip()


def validate_structured_html(html_content: str, spec: dict, *, expected_revision: int | None = None) -> None:
    inspector = _StructuredHtmlInspector()
    try:
        inspector.feed(html_content)
    except Exception as exc:
        raise _validation_error(f"HTML 無法解析: {exc}")

    required_ids = {
        "custom-brand-logo",
        "custom-main-title",
        "structured-description",
        "structured-form",
        "structured-fields",
        "structured-submit",
    }
    missing = sorted(required_ids - inspector.ids)
    if missing:
        raise _validation_error(f"生成結果缺少必要結構: {', '.join(missing)}")
    duplicated = sorted(node_id for node_id in required_ids if inspector.id_counts.get(node_id) != 1)
    if duplicated:
        raise _validation_error(f"生成結果的必要結構重複: {', '.join(duplicated)}")
    if inspector.form_count != 1:
        raise _validation_error("新版頁面只能包含一個表單")
    expected_text = {
        "title": spec["page_title"],
        "custom-main-title": spec["main_title"],
        "structured-description": spec["description"],
        "structured-submit": spec["submit_text"],
    }
    for node_id, text in expected_text.items():
        if inspector.text(node_id) != text:
            raise _validation_error(f"生成結果的 {node_id} 文字與指定需求不一致")

    expected_fields = [field["id"] for field in spec["fields"]]
    if inspector.field_ids != expected_fields:
        raise _validation_error("生成結果的欄位數量、ID 或順序與指定需求不一致")
    if inspector.field_labels != [field["label"] for field in spec["fields"]]:
        raise _validation_error("生成結果的欄位名稱或順序與指定需求不一致")
    if inspector.input_count != len(expected_fields):
        raise _validation_error("生成結果包含規格以外的輸入欄位")
    if inspector.extra_form_control_count:
        raise _validation_error("生成結果包含規格以外的表單控制項")
    if inspector.event_attribute_count:
        raise _validation_error("新版頁面不可包含行內事件程式")
    if expected_revision is not None and inspector.form_revision != str(expected_revision):
        raise _validation_error("頁面修訂號與欄位規格不一致")

    for field, attributes in zip(spec["fields"], inspector.field_attributes):
        expected = _input_attributes(field)
        for name in ("type", "data-field-type", "data-mask-mode", "data-keep-chars"):
            if attributes.get(name) != expected.get(name):
                raise _validation_error(f"欄位 '{field['label']}' 的 {name} 屬性不符合規格")
        if attributes.get("name") is not None:
            raise _validation_error(f"欄位 '{field['label']}' 不可包含原生提交名稱")
        if ("required" in attributes) != field["required"]:
            raise _validation_error(f"欄位 '{field['label']}' 的必填設定不符合規格")
        if field["type"] in {"national_id", "phone", "custom"} and attributes.get("pattern") != expected.get("pattern"):
            raise _validation_error(f"欄位 '{field['label']}' 的格式驗證不符合規格")
    if STRUCTURED_SCRIPT_SOURCE not in inspector.script_sources:
        raise _validation_error("生成結果缺少新版表單記錄程式")
    if any("recordingLogin.js" in source for source in inspector.script_sources):
        raise _validation_error("新版頁面不可載入舊版完整值記錄程式")
    if inspector.script_sources != [STRUCTURED_SCRIPT_SOURCE] or inspector.inline_script_count != 1:
        raise _validation_error("新版頁面只能包含必要的記錄程式")
    if inspector.inline_scripts != ['const API_BASE_PATH = "{{ api_base_path }}";']:
        raise _validation_error("新版頁面的 API_BASE_PATH 設定不正確")


def enrich_custom_patterns(html_content: str, spec: dict) -> dict:
    inspector = _StructuredHtmlInspector()
    inspector.feed(html_content)
    if inspector.field_ids != [field["id"] for field in spec["fields"]]:
        raise _validation_error("生成結果的欄位與指定需求不一致")

    enriched = clone_page_spec(spec)
    for field, attributes in zip(enriched["fields"], inspector.field_attributes):
        if field["type"] != "custom":
            continue
        pattern = str(attributes.get("pattern") or "").strip()
        if not pattern or len(pattern) > 500:
            raise _validation_error(f"指定內容欄位 '{field['label']}' 缺少有效的格式規則")
        try:
            re.compile(pattern)
        except re.error:
            raise _validation_error(f"指定內容欄位 '{field['label']}' 的格式規則無效")
        field["validation_pattern"] = pattern
    return enriched


def build_structured_ai_instructions(spec: dict, style_prompt: str) -> str:
    fields_html = build_fields_html(spec)
    return f'''
[任務]
建立單一響應式 HTML 表單頁面。頁面風格需求：{style_prompt or "清楚、專業、易於填寫"}

[不可變更的結構契約]
- 必須保留以下 ID：custom-brand-logo、custom-main-title、structured-description、structured-form、structured-fields、structured-submit。
- 表單必須是 <form id="structured-form" data-spec-revision="1">，修訂號不得修改。
- structured-fields 內只能放置下方提供的欄位節點，欄位數量、順序與 data-* 不得增刪或修改。input 不可新增 name 屬性，以避免瀏覽器原生提交原始值。
- 指定內容欄位必須依文字規格補上單一 HTML pattern 屬性；除此之外不可改動欄位屬性。
- 每個欄位外層固定使用 class="structured-field"；你的 CSS 必須讓新增同 class 節點時自動維持版面。
- 不可加入其他 form、input、textarea、select 或自行提交資料的 JavaScript。
- 不可載入 recordingLogin.js。必須在 </body> 前保留指定的 API_BASE_PATH 與 {STRUCTURED_SCRIPT_NAME}。
- Logo 容器模式為 {spec["logo_mode"]}。模式為 ai 時可在 custom-brand-logo 內生成不含外部腳本的 SVG/文字標誌；none 或 upload 時必須保持空容器。

[固定內容]
<title>{escape(spec["page_title"])}</title>
<h1 id="custom-main-title">{escape(spec["main_title"])}</h1>
<p id="structured-description">{escape(spec["description"])}</p>
<div id="structured-fields">
{fields_html}
</div>
<button id="structured-submit" type="submit">{escape(spec["submit_text"])}</button>

[必要腳本]
<script>const API_BASE_PATH = "{{{{ api_base_path }}}}";</script>
<script src="{{{{ url_for('static', path='js/{STRUCTURED_SCRIPT_NAME}') }}}}"></script>

只回傳從 <!DOCTYPE html> 開始的完整 HTML，不要 Markdown 或解釋文字。
'''.strip()