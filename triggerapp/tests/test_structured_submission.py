import pytest

from app.services.structured_submission import (
    StructuredSubmissionError,
    parse_trigger_url,
    validate_submission,
)


SPEC = {
    "fields": [
        {
            "id": "phone",
            "label": "手機",
            "type": "phone",
            "required": True,
            "mask_mode": "keep_end",
            "keep_chars": 3,
        },
        {
            "id": "password",
            "label": "密碼",
            "type": "password",
            "required": True,
            "mask_mode": "password_status",
            "keep_chars": None,
        },
    ]
}


def test_parse_trigger_url_supports_proxy_prefix():
    assert parse_trigger_url("https://example.test/trigger/page/form_a/person_1") == ("form_a", "person_1")
    assert parse_trigger_url("https://example.test/qr/form_a/person_2") == ("form_a", "person_2")


def test_submission_accepts_masked_values_in_spec_order():
    result = validate_submission(SPEC, 2, [
        {"id": "phone", "value": "*******789"},
        {"id": "password", "value": "[password:filled]"},
    ], 2)
    assert result == "*******789 | [password:filled]"


@pytest.mark.parametrize(
    "fields",
    [
        [{"id": "password", "value": "[password:filled]"}, {"id": "phone", "value": "*******789"}],
        [{"id": "phone", "value": "0912345678"}, {"id": "password", "value": "[password:filled]"}],
        [{"id": "phone", "value": "*******789"}, {"id": "password", "value": "secret"}],
    ],
)
def test_submission_rejects_contract_violations(fields):
    with pytest.raises(StructuredSubmissionError):
        validate_submission(SPEC, 2, fields, 2)


def test_submission_rejects_stale_revision():
    with pytest.raises(StructuredSubmissionError, match="已更新"):
        validate_submission(SPEC, 1, [
            {"id": "phone", "value": "*******789"},
            {"id": "password", "value": "[password:filled]"},
        ], 2)


@pytest.mark.parametrize("masked_value", ["*23", "**3"])
def test_submission_accepts_new_and_legacy_short_masks(masked_value):
    short_spec = {
        "fields": [{
            "id": "code",
            "label": "代碼",
            "type": "text",
            "required": True,
            "mask_mode": "keep_end",
            "keep_chars": 6,
        }]
    }

    assert validate_submission(short_spec, 1, [{"id": "code", "value": masked_value}], 1) == masked_value


def test_submission_rejects_unmasked_short_value():
    short_spec = {
        "fields": [{
            "id": "code",
            "label": "代碼",
            "type": "text",
            "required": True,
            "mask_mode": "keep_end",
            "keep_chars": 6,
        }]
    }

    with pytest.raises(StructuredSubmissionError, match="遮罩格式"):
        validate_submission(short_spec, 1, [{"id": "code", "value": "123"}], 1)