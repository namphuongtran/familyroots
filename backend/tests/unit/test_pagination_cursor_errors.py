"""M9: decode_cursor/decode_fields_cursor must raise AppError(400, invalid_cursor) on
garbage input, not leak binascii.Error/ValueError/KeyError up to the ASGI catch-all
(which turns into an unhandled 500 — see test_cursor_validation.py for the HTTP-level
proof). RED today: both decoders raise the raw stdlib exception instead of AppError.
"""

import base64
import json
import uuid
from datetime import UTC, datetime

import pytest

from app.core.exceptions import AppError
from app.core.pagination import (
    decode_cursor,
    decode_fields_cursor,
    encode_cursor,
    encode_fields_cursor,
)

pytestmark = pytest.mark.unit


def test_decode_cursor_valid_round_trip():
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    record_id = uuid.uuid4()
    cursor = encode_cursor(created_at, record_id)

    decoded_created_at, decoded_id = decode_cursor(cursor)

    assert decoded_created_at == created_at
    assert decoded_id == record_id


def test_decode_fields_cursor_valid_round_trip():
    record_id = uuid.uuid4()
    cursor = encode_fields_cursor({"full_name": "Nguyen Van A", "id": str(record_id)})

    decoded = decode_fields_cursor(cursor)

    assert decoded == {"full_name": "Nguyen Van A", "id": str(record_id)}


def test_decode_cursor_garbage_raises_app_error_400_invalid_cursor():
    with pytest.raises(AppError) as exc_info:
        decode_cursor("%%%not-base64%%%")

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "invalid_cursor"


def test_decode_fields_cursor_garbage_raises_app_error_400_invalid_cursor():
    with pytest.raises(AppError) as exc_info:
        decode_fields_cursor("%%%not-base64%%%")

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "invalid_cursor"


def test_decode_cursor_valid_base64_wrong_json_shape_raises_app_error_400():
    """Valid base64 + valid JSON, but missing the expected keys — must still 400,
    not KeyError."""
    cursor = base64.urlsafe_b64encode(json.dumps({"foo": 1}).encode()).decode()

    with pytest.raises(AppError) as exc_info:
        decode_cursor(cursor)

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "invalid_cursor"
