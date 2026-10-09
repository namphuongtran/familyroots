#!/usr/bin/env python3
"""Read the hosted project's two auth email templates back and compare them with the files.

ADR-063 § 6. ``supabase/templates/confirmation.html`` and ``supabase/templates/recovery.html``
are the bodies of the Confirm signup and Reset Password emails. The hosted project gets them from
``supabase/supabase/config.toml``, by ``npx --yes supabase@2.120.0 config push --workdir supabase``.
A push says nothing about what the project then holds, and the dashboard's editor keeps no history,
so the owner runs this after every push. The procedure is ``docs/ops/supabase-hosted-project.md``
§ 4.

It reads ``GET https://api.supabase.com/v1/projects/{ref}/config/auth``, whose
``AuthConfigResponse_Output`` carries ``mailer_templates_confirmation_content`` and
``mailer_templates_recovery_content``, and compares each with its file **byte for byte**, as UTF-8.
A hosted copy that lost the file's final newline differs.

Usage, from the repository root. Standard library only, so any ``python3`` runs it::

    export SUPABASE_ACCESS_TOKEN=sbp_...
    python3 scripts/read_back_auth_email_templates.py --project-ref <ref>
    python3 scripts/read_back_auth_email_templates.py --response saved-auth-config.json

``--response`` compares a response saved earlier, so the comparison can be run without a token.
The token is a personal access token with ``auth:read``. Nothing is printed from it, and the
response is not written anywhere.

Exit status:

    0   both templates equal their files
    1   at least one differs; each one that differs is named on a ``DIFFERS <name>:`` line
    2   nothing was compared: no token, a malformed ref, or a response that could not be read
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "supabase" / "templates"

# The template's name in config.toml, which is also its file's stem and its field's infix.
TEMPLATE_NAMES = ("confirmation", "recovery")

API_URL = "https://api.supabase.com/v1/projects/{ref}/config/auth"

# A project ref is twenty lowercase letters. Checked so that a typo cannot reach another path.
_PROJECT_REF = re.compile(r"[a-z]{20}")


class ReadBackError(Exception):
    """Nothing was compared. ``main`` reports it and exits 2."""


def field_for(name: str) -> str:
    return f"mailer_templates_{name}_content"


def compare(response: Mapping[str, object]) -> dict[str, str | None]:
    """Each template's difference from its file, or ``None`` when the hosted body equals it."""
    verdicts: dict[str, str | None] = {}
    for name in TEMPLATE_NAMES:
        path = TEMPLATES_DIR / f"{name}.html"
        expected = path.read_bytes()
        hosted = response.get(field_for(name))
        if not isinstance(hosted, str):
            verdicts[name] = f"the response carries no {field_for(name)} (it holds {hosted!r})"
            continue
        actual = hosted.encode("utf-8")
        if actual == expected:
            verdicts[name] = None
            continue
        at = next(
            (i for i, (a, b) in enumerate(zip(actual, expected, strict=False)) if a != b),
            min(len(actual), len(expected)),
        )
        verdicts[name] = (
            f"differs from {path.name} from byte {at} "
            f"(hosted {len(actual)} bytes, file {len(expected)} bytes)"
        )
    return verdicts


def fetch(project_ref: str, token: str) -> Mapping[str, object]:
    """The project's auth config, from the Management API."""
    request = urllib.request.Request(
        API_URL.format(ref=project_ref),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "familyroots-read-back-auth-email-templates",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            raw = answer.read()
    except urllib.error.HTTPError as exc:
        raise ReadBackError(f"GET {request.full_url} answered {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ReadBackError(f"GET {request.full_url} failed: {exc.reason}") from exc
    return _parse(raw, request.full_url)


def load(path: Path) -> Mapping[str, object]:
    """A response saved earlier."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReadBackError(f"cannot read {path}: {exc}") from exc
    return _parse(raw, str(path))


def _parse(raw: bytes, source: str) -> Mapping[str, object]:
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise ReadBackError(f"{source} is not JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ReadBackError(f"{source} is not a JSON object")
    return body


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project-ref", help="fetch from this project, with SUPABASE_ACCESS_TOKEN")
    source.add_argument("--response", type=Path, help="compare a saved response instead")
    args = parser.parse_args(argv)

    try:
        if args.response is not None:
            response = load(args.response)
        else:
            if not _PROJECT_REF.fullmatch(args.project_ref):
                raise ReadBackError(
                    f"{args.project_ref!r} is not a project ref (twenty lowercase letters)"
                )
            token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
            if not token:
                raise ReadBackError("SUPABASE_ACCESS_TOKEN is not set")
            response = fetch(args.project_ref, token)
    except ReadBackError as exc:
        print(f"read-back: {exc}", file=sys.stderr)
        return 2

    verdicts = compare(response)
    for name, difference in verdicts.items():
        print(f"match {name}" if difference is None else f"DIFFERS {name}: {difference}")
    return 0 if all(difference is None for difference in verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
