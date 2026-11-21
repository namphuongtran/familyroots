"""Keep credential path segments out of logs and Sentry.

An invitation token in ``/api/v1/invitations/{token}/accept`` is the authorization to join a
clan, so it must never be written to a log line or a Sentry event. Every other path stays raw,
so ``/persons/<uuid>`` keeps one distinct route per person.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "{token}"
_CREDENTIAL_NAMES = frozenset({"token", "vars"})

# One entry per route whose path carries a credential. Matches inside a longer string too
# (a full URL, a transaction name, a breadcrumb message), so the same pattern scrubs them all.
_CREDENTIAL_SEGMENTS = (re.compile(r"(/invitations/)[^/\s?#\"']+(/accept)"),)


def redact_path(text: str) -> str:
    """Replace each credential segment in ``text`` with a fixed placeholder."""
    for pattern in _CREDENTIAL_SEGMENTS:
        text = pattern.sub(rf"\g<1>{REDACTED}\g<2>", text)
    return text


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return redact_path(value)
    if isinstance(value, dict):
        # path_params carries the segment under its parameter name, and a stack frame's
        # "vars" holds reprs of locals (the handler's own ``token`` argument, a solved
        # dependency) that no pattern can reliably find, so both are dropped whole.
        return {k: "[Filtered]" if k in _CREDENTIAL_NAMES else _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def scrub_sentry_event(event: Any, hint: Any = None) -> Any:
    """``before_send`` / ``before_send_transaction`` hook: scrub the whole event."""
    return _scrub(event)
