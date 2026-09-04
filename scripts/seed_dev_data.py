#!/usr/bin/env python3
"""Seed the local development stack with a test clan, its users and their roles.

A test user exists in **two databases at once** and this script is what keeps the two
halves in step:

* the **identity** lives in the local Supabase stack's ``auth.users`` (GoTrue), and
* the **membership, role and clan** live in the application database that Alembic migrates.

They are joined by the JWT ``sub`` claim. If the two halves disagree, the login succeeds
and every clan-scoped request then answers ``403 no_approved_clan_membership`` — which
reads like an authorization bug and is not one. ``verify`` exists to name that.

**The halves join by construction, not by lookup.** Every seeded id below is a compile-time
constant, and GoTrue's admin API accepts an explicit ``id`` on create (measured against
``gotrue v2.195.0`` on 2026-08-22). So the application database can be seeded with the same
uuid the token will carry, without reading it back from Supabase first.

Usage (from ``backend/``, which owns the virtualenv that has ``psycopg`` and ``httpx2``)::

    cd backend
    uv run python ../scripts/seed_dev_data.py apply     # create both halves, then verify
    uv run python ../scripts/seed_dev_data.py verify    # check both halves, change nothing
    uv run python ../scripts/seed_dev_data.py dump      # canonical state, for a diff

``make seed`` is ``apply`` with `alembic upgrade head` in front of it and the local
defaults already exported; ``make seed-verify`` is ``verify``. Both are one command.

Environment:

    DATABASE_URL                the application database (``pgdb``). SQLAlchemy-style
                                ``+driver`` suffixes are stripped before libpq sees it.
    SUPABASE_URL                the local stack's gateway. MUST be
                                ``http://supabase.localhost:54321`` — a ``127.0.0.1``
                                value issues tokens the backend rejects with
                                ``401 invalid_token``. See docs/ops/local-supabase.md.
    SUPABASE_SERVICE_ROLE_KEY   from ``scripts/supabase_local.sh env``.

What this script does NOT seed: persons, marriages, parent-child links, documents and
events. A role check needs none of them, and they are out of scope on purpose —
fixtures for a tree belong to the test that asserts something about a tree, not here.
``clan_memberships`` is likewise untouched: it links a **Person** to a clan, not a user,
so it cannot be written without inventing person fixtures.
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx2
import psycopg

# ── The fixture ───────────────────────────────────────────────────────────────
#
# Two clans, because clan isolation cannot be tested from inside one clan — that is the
# two-sided rule every RLS test in this repository follows.

# A local dev stack only, never a real one. The seeder refuses any non-local SUPABASE_URL.
TEST_PASSWORD = "dev-password-s073"

# `familyroots.example.com`, and NOT `familyroots.test`, which was the obvious choice and
# does not work. Measured 2026-08-22: GoTrue creates an identity at a `.test` address
# happily, and then `POST /api/v1/auth/login` answers
# `422 {"error":{"code":"validation_error","detail":{"fields":["body.email"]}}}` before it
# ever reaches Supabase. `LoginRequest.email` is a Pydantic `EmailStr`
# (app/schemas/auth.py:45-46), and email_validator rejects `.test` and `.local` as
# "a special-use or reserved name that cannot be used with email". `example.com` is
# reserved by RFC 2606 for exactly this, its subdomains pass the validator, and mail to it
# cannot reach a real party. That is the whole reason for the longer domain.
EMAIL_DOMAIN = "familyroots.example.com"


@dataclass(frozen=True)
class ClanSpec:
    id: uuid.UUID
    slug: str
    name: str
    description: str


@dataclass(frozen=True)
class UserSpec:
    id: uuid.UUID
    email: str
    display_name: str
    clan: ClanSpec
    role: str


CLAN_A = ClanSpec(
    id=uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001"),
    slug="nguyen-phuc",
    name="Nguyễn Phúc",
    description="Dòng họ thử nghiệm chính. The clan under test.",
)
CLAN_B = ClanSpec(
    id=uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002"),
    slug="tran-gia",
    name="Trần Gia",
    description="Dòng họ thứ hai. Exists so isolation has a second side.",
)

CLANS: tuple[ClanSpec, ...] = (CLAN_A, CLAN_B)

USERS: tuple[UserSpec, ...] = (
    UserSpec(
        id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        email=f"admin@{EMAIL_DOMAIN}",
        display_name="Quản trị viên",
        clan=CLAN_A,
        role="admin",
    ),
    UserSpec(
        id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        email=f"editor@{EMAIL_DOMAIN}",
        display_name="Biên tập viên",
        clan=CLAN_A,
        role="editor",
    ),
    UserSpec(
        id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        email=f"viewer@{EMAIL_DOMAIN}",
        display_name="Người xem",
        clan=CLAN_A,
        role="viewer",
    ),
    # The second side. Deliberately a member of CLAN_B and of nothing else: a user who
    # belonged to both clans would make `get_current_clan_id` answer
    # `400 multiple_clans_no_selection` whenever a caller omitted X-Current-Clan-Id
    # (app/core/security.py), which every e2e test would then have to work around.
    UserSpec(
        id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
        email=f"outsider@{EMAIL_DOMAIN}",
        display_name="Người họ khác",
        clan=CLAN_B,
        role="admin",
    ),
)

# ── SQL. Every statement this script runs against the application database ────
#
# Listed as named constants so that the set is enumerable by reading this block, and so a
# guard over scripts/ can see them. Nothing else here executes SQL.

SQL_ASSERT_SCHEMA = """
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = ANY(%(names)s)
"""

# Every upsert carries a WHERE guard on the DO UPDATE branch, so a row that already
# matches the fixture is not rewritten and its `updated_at` does not move. That is what
# makes "run it twice, diff the state" an exact claim rather than an approximate one:
# the second run writes nothing at all, and `dump` includes the timestamps to prove it.

SQL_UPSERT_CLAN = """
INSERT INTO clans (id, name, slug, description, is_active, created_at, updated_at)
VALUES (%(id)s, %(name)s, %(slug)s, %(description)s, TRUE, NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    description = EXCLUDED.description,
    is_active = TRUE,
    updated_at = NOW()
WHERE clans.name IS DISTINCT FROM EXCLUDED.name
   OR clans.slug IS DISTINCT FROM EXCLUDED.slug
   OR clans.description IS DISTINCT FROM EXCLUDED.description
   OR clans.is_active IS DISTINCT FROM TRUE
"""

SQL_UPSERT_USER_PROFILE = """
INSERT INTO user_profiles
    (id, email, display_name, language, timezone, is_active, platform_role,
     created_at, updated_at)
VALUES
    (%(id)s, %(email)s, %(display_name)s, 'vi', 'Asia/Ho_Chi_Minh', TRUE, 'user',
     NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET email = EXCLUDED.email,
    display_name = EXCLUDED.display_name,
    is_active = TRUE,
    updated_at = NOW()
WHERE user_profiles.email IS DISTINCT FROM EXCLUDED.email
   OR user_profiles.display_name IS DISTINCT FROM EXCLUDED.display_name
   OR user_profiles.is_active IS DISTINCT FROM TRUE
"""

# `approved_by` is NOT NULL-able in practice: ck_user_clan_roles_..._approval_consistency
# requires is_approved = true to come with both approved_by and approved_at. The seeded
# approver is the clan's own admin, and that admin's row is self-approved — which is what
# a bootstrapped clan looks like anyway.
SQL_UPSERT_USER_CLAN_ROLE = """
INSERT INTO user_clan_roles
    (id, clan_id, user_id, role, is_approved, approved_by, approved_at,
     created_at, updated_at)
VALUES
    (%(id)s, %(clan_id)s, %(user_id)s, %(role)s, TRUE, %(approved_by)s, NOW(),
     NOW(), NOW())
ON CONFLICT (user_id, clan_id) DO UPDATE
SET role = EXCLUDED.role,
    is_approved = TRUE,
    approved_by = EXCLUDED.approved_by,
    approved_at = COALESCE(user_clan_roles.approved_at, NOW()),
    updated_at = NOW()
WHERE user_clan_roles.role IS DISTINCT FROM EXCLUDED.role
   OR user_clan_roles.is_approved IS DISTINCT FROM TRUE
   OR user_clan_roles.approved_by IS DISTINCT FROM EXCLUDED.approved_by
"""

SQL_SELECT_CLANS = """
SELECT id, slug, name, is_active, created_at, updated_at
FROM clans WHERE id = ANY(%(ids)s) ORDER BY slug
"""

SQL_SELECT_PROFILES = """
SELECT id, email, display_name, is_active, platform_role, created_at, updated_at
FROM user_profiles WHERE id = ANY(%(ids)s) OR email = ANY(%(emails)s)
ORDER BY email
"""

SQL_SELECT_ROLES = """
SELECT user_id, clan_id, role, is_approved, approved_by, created_at, updated_at
FROM user_clan_roles WHERE user_id = ANY(%(ids)s)
ORDER BY user_id, clan_id
"""

# The role row's own id is derived, not random, so that `apply` twice writes the same
# primary key and `dump` is byte-identical across runs.
_ROLE_ID_NAMESPACE = uuid.UUID("5eed0073-0000-4000-8000-000000000000")


def role_row_id(user: UserSpec) -> uuid.UUID:
    return uuid.uuid5(_ROLE_ID_NAMESPACE, f"{user.id}:{user.clan.id}")


def clan_admin_id(clan: ClanSpec) -> uuid.UUID:
    """The seeded admin of *clan*, used as `approved_by`. Every clan below has one."""
    for user in USERS:
        if user.clan is clan and user.role == "admin":
            return user.id
    raise AssertionError(f"clan {clan.slug!r} has no seeded admin to approve its members")


# ── Configuration, read loudly ────────────────────────────────────────────────

_LOCAL_HOSTS = ("supabase.localhost", "127.0.0.1", "localhost", "host.docker.internal")


class ConfigError(RuntimeError):
    pass


def _require_env(name: str, hint: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. {hint}")
    return value


def app_dsn() -> str:
    """The application database DSN, with any SQLAlchemy ``+driver`` suffix removed."""
    raw = _require_env(
        "DATABASE_URL",
        "It is the application database (pgdb), e.g. "
        "postgresql://postgres:postgres@localhost:5432/family_roots",
    )
    return re.sub(r"^(postgresql|postgres)\+[a-z0-9_]+://", r"\1://", raw)


def supabase_config() -> tuple[str, str]:
    url = _require_env(
        "SUPABASE_URL",
        "Run `scripts/supabase_local.sh env`. It must be "
        "http://supabase.localhost:54321 — a 127.0.0.1 value issues tokens the backend "
        "rejects with 401 invalid_token (docs/ops/local-supabase.md).",
    ).rstrip("/")
    key = _require_env("SUPABASE_SERVICE_ROLE_KEY", "Run `scripts/supabase_local.sh env`.")
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    if host not in _LOCAL_HOSTS:
        raise ConfigError(
            f"SUPABASE_URL points at {host!r}, which is not a local stack. This script "
            f"creates users with a published password and is for local development only. "
            f"Refusing to touch anything but {', '.join(_LOCAL_HOSTS)}."
        )
    return url, key


# ── The Supabase half ─────────────────────────────────────────────────────────


class GoTrue:
    """The GoTrue admin API, which owns ``auth.users``."""

    _RETRY_STATUSES = frozenset({502, 503, 504})
    _MAX_ATTEMPTS = 4
    _BACKOFF_SECONDS = 3.0

    def __init__(self, url: str, service_role_key: str) -> None:
        self._base = f"{url}/auth/v1"
        self._client = httpx2.Client(
            timeout=30.0,
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx2.Response:
        """One admin call, retried while the gateway says it is not ready yet.

        A cold stack answers the first admin write with ``504 request_timeout`` and the
        same call in 0.16 s a minute later — a known trap recorded in
        docs/ops/local-supabase.md and measured twice on 2026-08-22. Retrying a bounded
        number of times is the difference between this script being usable right after
        ``supabase_local.sh up`` and not. Only 502/503/504 and transport errors are
        retried: a 4xx is an answer, and repeating it would only hide it.
        """
        last: Exception | None = None
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                resp = self._client.request(method, f"{self._base}{path}", **kwargs)
                if resp.status_code not in self._RETRY_STATUSES:
                    return resp
                last = httpx2.HTTPStatusError(
                    f"{resp.status_code} from {method} {path}",
                    request=resp.request,
                    response=resp,
                )
            except httpx2.TransportError as exc:
                last = exc
            if attempt < self._MAX_ATTEMPTS:
                print(
                    f"seed_dev_data: the Supabase stack is not ready "
                    f"({method} {path}, attempt {attempt}/{self._MAX_ATTEMPTS}). "
                    f"Retrying in {self._BACKOFF_SECONDS:.0f}s.",
                    file=sys.stderr,
                )
                time.sleep(self._BACKOFF_SECONDS)
        assert last is not None
        raise last

    def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        resp = self._request("GET", f"/admin/users/{user_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return body

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        """Used only to detect drift: an identity holding a fixture email under a
        different id, which is what a re-created stack plus a stale app database looks
        like."""
        resp = self._request("GET", "/admin/users", params={"per_page": 200})
        resp.raise_for_status()
        for user in resp.json().get("users", []):
            if user.get("email") == email:
                found: dict[str, Any] = user
                return found
        return None

    def upsert_user(self, user: UserSpec) -> str:
        """Create, repair, or leave alone the identity at its fixed id.

        Returns ``created`` | ``repaired`` | ``unchanged``. An identity that already
        matches the fixture is **not** written, so a second ``apply`` moves no
        ``auth.users.updated_at`` — the same exactness the SQL upserts have.

        One consequence, stated plainly: the password is set on ``created`` and on
        ``repaired`` only. If someone changed a fixture user's password by hand, this
        will not notice, because a password cannot be read back. Delete that user from
        ``auth.users`` and run ``apply`` again.
        """
        payload = {
            "email": user.email,
            "password": TEST_PASSWORD,
            "email_confirm": True,
            "user_metadata": {"full_name": user.display_name, "preferred_locale": "vi"},
        }
        existing = self.get_user(user.id)
        if existing is None:
            resp = self._request("POST", "/admin/users", json={"id": str(user.id), **payload})
            resp.raise_for_status()
            return "created"
        matches = (
            existing.get("email") == user.email
            and bool(existing.get("email_confirmed_at"))
            and existing.get("user_metadata", {}).get("full_name") == user.display_name
        )
        if matches:
            return "unchanged"
        resp = self._request("PUT", f"/admin/users/{user.id}", json=payload)
        resp.raise_for_status()
        return "repaired"


# ── The application-database half ─────────────────────────────────────────────

_REQUIRED_TABLES = ["clans", "user_profiles", "user_clan_roles"]


def assert_schema(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(SQL_ASSERT_SCHEMA, {"names": _REQUIRED_TABLES})
        present = {row[0] for row in cur.fetchall()}
    missing = sorted(set(_REQUIRED_TABLES) - present)
    if missing:
        raise ConfigError(
            f"The application database is missing {', '.join(missing)}. It has not been "
            f"migrated. Run `cd backend && uv run alembic upgrade head` against this "
            f"DATABASE_URL first."
        )


def apply_app_database(conn: psycopg.Connection[Any]) -> dict[str, int]:
    """Write the clan, profile and role halves. Idempotent by upsert on fixed ids.

    Returns the number of rows each statement actually wrote. On a second run every
    count is 0, because each ``DO UPDATE`` carries a ``WHERE`` guard — reporting the
    fixture size instead would say "4 roles" on a run that touched nothing.
    """
    written = {"clans": 0, "user_profiles": 0, "user_clan_roles": 0}
    with conn.cursor() as cur:
        for clan in CLANS:
            cur.execute(
                SQL_UPSERT_CLAN,
                {
                    "id": str(clan.id),
                    "name": clan.name,
                    "slug": clan.slug,
                    "description": clan.description,
                },
            )
            written["clans"] += cur.rowcount
        for user in USERS:
            cur.execute(
                SQL_UPSERT_USER_PROFILE,
                {
                    "id": str(user.id),
                    "email": user.email,
                    "display_name": user.display_name,
                },
            )
            written["user_profiles"] += cur.rowcount
            cur.execute(
                SQL_UPSERT_USER_CLAN_ROLE,
                {
                    "id": str(role_row_id(user)),
                    "clan_id": str(user.clan.id),
                    "user_id": str(user.id),
                    "role": user.role,
                    "approved_by": str(clan_admin_id(user.clan)),
                },
            )
            written["user_clan_roles"] += cur.rowcount
    conn.commit()
    return written


def read_app_database(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    ids = [str(u.id) for u in USERS]
    emails = [u.email for u in USERS]
    with conn.cursor() as cur:
        cur.execute(SQL_SELECT_CLANS, {"ids": [str(c.id) for c in CLANS]})
        clans = [
            {
                "id": str(r[0]),
                "slug": r[1],
                "name": r[2],
                "is_active": r[3],
                "created_at": r[4].isoformat(),
                "updated_at": r[5].isoformat(),
            }
            for r in cur.fetchall()
        ]
        cur.execute(SQL_SELECT_PROFILES, {"ids": ids, "emails": emails})
        profiles = [
            {
                "id": str(r[0]),
                "email": r[1],
                "display_name": r[2],
                "is_active": r[3],
                "platform_role": r[4],
                "created_at": r[5].isoformat(),
                "updated_at": r[6].isoformat(),
            }
            for r in cur.fetchall()
        ]
        cur.execute(SQL_SELECT_ROLES, {"ids": ids})
        roles = [
            {
                "user_id": str(r[0]),
                "clan_id": str(r[1]),
                "role": r[2],
                "is_approved": r[3],
                "approved_by": str(r[4]),
                "created_at": r[5].isoformat(),
                "updated_at": r[6].isoformat(),
            }
            for r in cur.fetchall()
        ]
    return {"clans": clans, "user_profiles": profiles, "user_clan_roles": roles}


# ── Verification: the part that names the missing half ────────────────────────

_CONSEQUENCE = (
    "this user CAN log in, and every clan-scoped request then answers\n"
    '                 403 {"error":{"code":"no_approved_clan_membership",...}}.\n'
    "                 That is NOT a permissions bug. It is the missing row named above."
)


def verify(conn: psycopg.Connection[Any], gotrue: GoTrue, supabase_url: str) -> list[str]:
    """Return a list of human-readable problems. Empty means the halves are in step."""
    problems: list[str] = []
    state = read_app_database(conn)

    clans_by_id = {c["id"]: c for c in state["clans"]}
    for clan in CLANS:
        row = clans_by_id.get(str(clan.id))
        if row is None:
            problems.append(
                f"clan {clan.slug!r} ({clan.id})\n"
                f"    clan row   : MISSING  from the application database's `clans`\n"
                f"    fix        : re-run `scripts/seed_dev_data.py apply`"
            )
        elif not row["is_active"]:
            problems.append(
                f"clan {clan.slug!r} ({clan.id})\n"
                f"    clan row   : PRESENT but is_active = false, so every member gets\n"
                f"                 403 clan_suspended (app/core/security.py)."
            )

    profiles_by_id = {p["id"]: p for p in state["user_profiles"]}
    profiles_by_email = {p["email"]: p for p in state["user_profiles"]}
    roles_by_user = {r["user_id"]: r for r in state["user_clan_roles"]}

    for user in USERS:
        identity = gotrue.get_user(user.id)
        head = f"{user.email} (id {user.id})"

        if identity is None:
            stray = gotrue.find_by_email(user.email)
            detail = (
                f"    identity   : MISSING  from the Supabase stack's auth.users ({supabase_url})\n"
            )
            if stray is not None:
                detail += (
                    f"                 but an identity with this email exists under a "
                    f"DIFFERENT id: {stray.get('id')}.\n"
                    f"                 The stack was re-created while the application "
                    f"database kept the old rows.\n"
                )
            fix = (
                "    fix        : `apply` CANNOT repair this — GoTrue would answer 422 "
                "email_exists.\n"
                f"                 Delete identity {stray.get('id')} from auth.users, or run\n"
                "                 `scripts/supabase_local.sh destroy`, then `apply`."
                if stray is not None
                else "    fix        : re-run `scripts/seed_dev_data.py apply`"
            )
            problems.append(f"{head}\n{detail}{fix}")
        elif not identity.get("email_confirmed_at"):
            problems.append(
                f"{head}\n"
                f"    identity   : PRESENT but UNCONFIRMED in auth.users. The password "
                f"grant answers\n"
                f"                 400 email_not_confirmed, so this user cannot log in "
                f"at all.\n"
                f"    fix        : re-run `scripts/seed_dev_data.py apply`"
            )

        profile = profiles_by_id.get(str(user.id))
        if profile is None:
            collision = profiles_by_email.get(user.email)
            detail = "    profile    : MISSING  from the application database's `user_profiles`\n"
            if collision is not None:
                detail += (
                    f"                 and a row with this email exists under a "
                    f"DIFFERENT id: {collision['id']}.\n"
                    f"                 `user_profiles.email` is UNIQUE, so `apply` "
                    f"cannot repair this on its own.\n"
                    f"                 Delete that row, or drop and re-migrate the "
                    f"application database.\n"
                )
            fix = (
                "    fix        : delete that row first, then run `scripts/seed_dev_data.py apply`"
                if collision is not None
                else "    fix        : re-run `scripts/seed_dev_data.py apply`"
            )
            problems.append(f"{head}\n{detail}    consequence: {_CONSEQUENCE}\n{fix}")
        elif not profile["is_active"]:
            problems.append(
                f"{head}\n"
                f"    profile    : PRESENT but is_active = false, so every "
                f"authenticated request\n"
                f"                 answers 403 account_deactivated "
                f"(app/core/security.py)."
            )

        role = roles_by_user.get(str(user.id))
        if role is None:
            problems.append(
                f"{head}\n"
                f"    membership : MISSING  from the application database's "
                f"`user_clan_roles`\n"
                f"                 expected role {user.role!r} in clan "
                f"{user.clan.slug!r} ({user.clan.id})\n"
                f"    consequence: {_CONSEQUENCE}\n"
                f"    fix        : re-run `scripts/seed_dev_data.py apply`"
            )
        else:
            if role["clan_id"] != str(user.clan.id) or role["role"] != user.role:
                problems.append(
                    f"{head}\n"
                    f"    membership : WRONG. expected role {user.role!r} in clan "
                    f"{user.clan.id}, found\n"
                    f"                 role {role['role']!r} in clan {role['clan_id']}."
                )
            if not role["is_approved"]:
                problems.append(
                    f"{head}\n"
                    f"    membership : PRESENT but is_approved = false, which "
                    f"`get_current_clan_id`\n"
                    f"                 filters out.\n"
                    f"    consequence: {_CONSEQUENCE}"
                )

    return problems


# ── Commands ──────────────────────────────────────────────────────────────────


def summary() -> str:
    lines = ["", "Seeded (password for every user: " + TEST_PASSWORD + ")", ""]
    lines.append(f"  {'email':<32} {'clan':<14} {'role':<8} id")
    for user in USERS:
        lines.append(f"  {user.email:<32} {user.clan.slug:<14} {user.role:<8} {user.id}")
    lines.append("")
    lines.append(f"  {CLAN_A.slug} = {CLAN_A.id}   (X-Current-Clan-Id for the three role users)")
    lines.append(
        f"  {CLAN_B.slug} = {CLAN_B.id}   (the second side; only {USERS[3].email} is in it)"
    )
    return "\n".join(lines)


def assert_no_email_drift(gotrue: GoTrue) -> None:
    """Refuse to write anything while a fixture email is held under a different id.

    This is the one drift `apply` cannot repair, so it must be named rather than hit. It
    is what a re-created Supabase stack looks like from here: the fixture id is gone, the
    email is taken by whatever id the new stack minted, and creating the fixture id then
    fails with `422 email_exists` from GoTrue halfway through the run. Measured
    2026-08-22 by planting exactly that.
    """
    drifted: list[str] = []
    for user in USERS:
        if gotrue.get_user(user.id) is not None:
            continue
        stray = gotrue.find_by_email(user.email)
        if stray is not None:
            drifted.append(
                f"  {user.email}\n"
                f"    expected id : {user.id}  (absent from auth.users)\n"
                f"    found id    : {stray.get('id')}  (holds this email)"
            )
    if not drifted:
        return
    raise ConfigError(
        "a fixture email is registered under a different id, so `apply` cannot proceed.\n"
        "  GoTrue would answer 422 email_exists partway through, leaving half a run.\n\n"
        + "\n".join(drifted)
        + "\n\n  This is what a re-created Supabase stack beside a kept application\n"
        "  database looks like. Two ways out, and neither is `apply`:\n"
        "    - delete the identity that holds the email (admin API DELETE /admin/users/<id>), or\n"
        "    - `scripts/supabase_local.sh destroy` to clear auth.users entirely,\n"
        "  then run `apply` again."
    )


def cmd_apply(conn: psycopg.Connection[Any], gotrue: GoTrue, supabase_url: str) -> int:
    assert_schema(conn)
    assert_no_email_drift(gotrue)
    for user in USERS:
        action = gotrue.upsert_user(user)
        print(f"seed_dev_data: auth.users  {action:<7} {user.email}")
    written = apply_app_database(conn)
    print(
        "seed_dev_data: app database rows written  "
        + ", ".join(f"{table} {count}" for table, count in written.items())
    )
    exit_code = cmd_verify(conn, gotrue, supabase_url, quiet_ok=True)
    if exit_code == 0:
        print(summary())
    return exit_code


def cmd_verify(
    conn: psycopg.Connection[Any],
    gotrue: GoTrue,
    supabase_url: str,
    *,
    quiet_ok: bool = False,
) -> int:
    assert_schema(conn)
    problems = verify(conn, gotrue, supabase_url)
    if not problems:
        if not quiet_ok:
            print(
                f"seed_dev_data: both halves agree — {len(USERS)} users across {len(CLANS)} clans."
            )
        return 0
    print("", file=sys.stderr)
    print("seed_dev_data: THE TWO HALVES DISAGREE.", file=sys.stderr)
    print(
        "  An identity in the Supabase stack without its row in the application "
        "database\n"
        "  is a user who logs in successfully and can then reach nothing.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
        print("", file=sys.stderr)
    print(
        f"seed_dev_data: {len(problems)} problem(s). Exit 1.",
        file=sys.stderr,
    )
    return 1


def cmd_dump(conn: psycopg.Connection[Any], gotrue: GoTrue) -> int:
    identities = []
    for user in USERS:
        row = gotrue.get_user(user.id)
        identities.append(
            {
                "id": str(user.id),
                "present": row is not None,
                "email": None if row is None else row.get("email"),
                "confirmed": None if row is None else bool(row.get("email_confirmed_at")),
                "role": None if row is None else row.get("role"),
                "created_at": None if row is None else row.get("created_at"),
                # Included on purpose: it is what proves a second `apply` wrote nothing
                # to auth.users either, not only to the application database.
                "updated_at": None if row is None else row.get("updated_at"),
            }
        )
    state = {"auth_users": identities, "app_database": read_app_database(conn)}
    print(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="seed_dev_data.py",
        description=("Seed a test clan, its users and their roles into BOTH local databases."),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="apply",
        choices=("apply", "verify", "dump"),
        help=(
            "apply: create both halves then verify (default). "
            "verify: check both halves, change nothing. "
            "dump: canonical JSON state of both halves, for a diff."
        ),
    )
    args = parser.parse_args()

    try:
        dsn = app_dsn()
        supabase_url, service_key = supabase_config()
    except ConfigError as exc:
        print(f"seed_dev_data: {exc}", file=sys.stderr)
        return 2

    gotrue = GoTrue(supabase_url, service_key)
    try:
        with psycopg.connect(dsn) as conn:
            if args.command == "apply":
                return cmd_apply(conn, gotrue, supabase_url)
            if args.command == "verify":
                return cmd_verify(conn, gotrue, supabase_url)
            return cmd_dump(conn, gotrue)
    except ConfigError as exc:
        print(f"seed_dev_data: {exc}", file=sys.stderr)
        return 2
    except psycopg.OperationalError as exc:
        print(
            f"seed_dev_data: cannot reach the application database.\n"
            f"  DATABASE_URL host is unreachable: {exc}\n"
            f"  Start it with `docker compose up -d pgdb`.",
            file=sys.stderr,
        )
        return 2
    except httpx2.HTTPStatusError as exc:
        # The stack answered. Saying "cannot reach it" here would send the reader to
        # `supabase_local.sh up` for a problem that has nothing to do with the stack
        # being down — which is exactly what this script exists to stop happening.
        print(
            f"seed_dev_data: the Supabase stack at {supabase_url} refused a request.\n"
            f"  {exc.request.method} {exc.request.url.path} -> "
            f"{exc.response.status_code}\n"
            f"  {exc.response.text[:500]}",
            file=sys.stderr,
        )
        return 2
    except httpx2.HTTPError as exc:
        print(
            f"seed_dev_data: cannot reach the Supabase stack at {supabase_url}.\n"
            f"  {exc}\n"
            f"  Start it with `scripts/supabase_local.sh up`.",
            file=sys.stderr,
        )
        return 2
    finally:
        gotrue.close()


if __name__ == "__main__":
    raise SystemExit(main())
