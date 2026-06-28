"""Log records must serialize to valid JSON even with quotes/newlines."""

import json
import logging

from app.core.logging import JsonFormatter


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_message_with_quotes_is_valid_json():
    out = JsonFormatter().format(_record('he said "hi"\nthen left'))
    parsed = json.loads(out)  # must not raise
    assert parsed["message"] == 'he said "hi"\nthen left'
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert "time" in parsed
