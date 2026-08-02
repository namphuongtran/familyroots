"""Structured JSON logging configuration."""

import json
import logging
import sys

from app.core.config import settings
from app.core.trace_context import get_trace_context


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single valid JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Correlation fields, present only inside a request. Absent (not null) for
        # scheduler/purge work so a log query for trace_id never matches system jobs.
        ctx = get_trace_context()
        if ctx is not None:
            payload["trace_id"] = ctx.trace_id
            payload["span_id"] = ctx.span_id
            if ctx.route is not None:
                payload["route"] = ctx.route
            if ctx.clan_id is not None:
                payload["clan_id"] = ctx.clan_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Set up structured logging with JSON-compatible format."""
    level = logging.DEBUG if settings.APP_DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.APP_DEBUG else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
