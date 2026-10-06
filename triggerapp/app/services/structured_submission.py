from urllib.parse import urlparse


MAX_FIELD_VALUE_LENGTH = 2000


class StructuredSubmissionError(ValueError):
    pass


def parse_trigger_url(raw_url: str) -> tuple[str, str]:
    path_parts = [part for part in urlparse(raw_url).path.split("/") if part]
    for marker in ("page", "qr"):
        if marker not in path_parts:
            continue
        marker_index = path_parts.index(marker)
        if len(path_parts) > marker_index + 2:
            return path_parts[marker_index + 1], path_parts[marker_index + 2][:64]
    raise StructuredSubmissionError("無法辨識表單頁面網址")


def _validate_masked_value(value: str, field: dict) -> None:
    if len(value) > MAX_FIELD_VALUE_LENGTH:
        raise StructuredSubmissionError(f"欄位 '{field['label']}' 的內容過長")

    field_type = field.get("type")
    mode = field.get("mask_mode", "full")
    required = bool(field.get("required"))
    if not value:
        if required:
            raise StructuredSubmissionError(f"欄位 '{field['label']}' 為必填")
        return
    if mode == "none":
        return
    if mode == "full":
        if set(value) != {"*"}:
            raise StructuredSubmissionError(f"欄位 '{field['label']}' 未完整遮罩")
        return

    keep_chars = int(field.get("keep_chars") or 1)
    length = len(value)
    if length == 1:
        valid = value == "*"
    elif length <= keep_chars:
        if mode == "keep_start":
            valid = value.endswith("*") or value[1:] == "*" * (length - 1)
        else:
            valid = value.startswith("*") or value[:-1] == "*" * (length - 1)
    elif mode == "keep_start":
        valid = value[keep_chars:] == "*" * (length - keep_chars)
    elif mode == "keep_end":
        valid = value[:-keep_chars] == "*" * (length - keep_chars)
    else:
        valid = False
    if not valid:
        raise StructuredSubmissionError(f"欄位 '{field['label']}' 的遮罩格式不正確")


def validate_submission(spec: dict, revision: int, submitted_fields: list[dict], expected_revision: int) -> str:
    if revision != expected_revision:
        raise StructuredSubmissionError("頁面規格已更新，請重新整理後再送出")
    expected_fields = spec.get("fields") or []
    if len(submitted_fields) != len(expected_fields):
        raise StructuredSubmissionError("送出的欄位數量與頁面規格不一致")

    values = []
    for expected, submitted in zip(expected_fields, submitted_fields):
        if submitted.get("id") != expected.get("id"):
            raise StructuredSubmissionError("送出的欄位順序與頁面規格不一致")
        value = submitted.get("value")
        if not isinstance(value, str):
            raise StructuredSubmissionError(f"欄位 '{expected['label']}' 的內容格式不正確")
        _validate_masked_value(value, expected)
        values.append(value)
    return " | ".join(values)