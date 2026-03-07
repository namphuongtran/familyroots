"""Cursor-based pagination utilities.

Uses (created_at, id) composite cursor for stable pagination
even when rows are inserted mid-page.
"""

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, asc, or_


def encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    """Encode a (created_at, id) pair into a base64 cursor string."""
    payload = {"created_at": created_at.isoformat(), "id": str(record_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode a base64 cursor string back into (created_at, id)."""
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])


def paginate_query(query: Any, model: Any, cursor: str | None, limit: int = 20) -> Any:
    """Apply cursor filter and ordering to a SQLAlchemy select query.

    Always orders by (created_at ASC, id ASC) for stable pagination.
    Fetches ``limit + 1`` rows to detect whether more pages exist.
    """
    if cursor:
        created_at, last_id = decode_cursor(cursor)
        query = query.where(
            or_(
                model.created_at > created_at,
                and_(model.created_at == created_at, model.id > last_id),
            )
        )
    return query.order_by(asc(model.created_at), asc(model.id)).limit(limit + 1)


def build_page(items: list[Any], limit: int) -> dict[str, Any]:
    """Build a paginated response envelope from a list of ORM objects.

    If ``len(items) > limit``, a cursor is generated pointing to the
    last item in the returned page so the client can fetch the next page.
    """
    has_more = len(items) > limit
    data = items[:limit]
    cursor = None
    if has_more and data:
        last = data[-1]
        cursor = encode_cursor(last.created_at, last.id)
    return {
        "data": data,
        "meta": {"cursor": cursor, "has_more": has_more, "limit": limit},
    }
