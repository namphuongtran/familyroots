# Notification Robustness (PR-H) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the anniversary notification job correct — real localized push text per user, no crash outside Supabase, non-blocking sends, per-event isolation, lunar events excluded (deferred), and truthful delivery logging.

**Architecture:** Small, surgical fixes to the two service files (`scheduler.py`, `notification.py`) plus the translator and i18n. No structural change; C2's lock/clock/leap-date work stays untouched.

**Tech Stack:** FastAPI, SQLAlchemy async/psycopg, PostgreSQL, APScheduler, Firebase FCM, `asyncio.to_thread`, pytest(-asyncio) against dockerized Postgres.

## Global Constraints

- C2 work (advisory lock topology, single `today` clock, `next_anniversary_sql`, tz) is DONE — do not modify it.
- Lunar events (`is_lunar_calendar = true`) are **excluded** from the job (owner decision); correct lunar support is deferred to data-model round 2. Do NOT implement lunar→solar conversion.
- i18n: notification keys become `notification.<type>.title` + `notification.<type>.body` in ALL FOUR locales (vi/en/zh/fr); body = the existing sentence verbatim. The all-locale parity guard must stay green.
- Notified recurring types: `death_anniversary`, `birthday`, `wedding_anniversary`.
- `user_profiles.language` (String(10), default `"vi"`) is the per-user locale source — never `auth.users`.
- S2-10 (missed-run window) is OUT OF SCOPE (documented follow-up).
- Branch `fix/notification-robustness` (already checked out). Do NOT `git add -A`. Run `./scripts/check.sh` before each commit. Commands from `backend/`.

---

### Task 1: translator `t(locale=…)` + per-send locale plumbing

**Files:**
- Modify: `app/services/translator.py` (`t` gains a keyword-only `locale`)
- Modify: `app/services/notification.py` (`send_push_notification` passes `locale` into `t`)
- Test: `tests/unit/test_translator_locale.py` (new)

**Interfaces:**
- Produces: `t(key: str, *, locale: str | None = None, **kwargs) -> str` — resolves with `locale or current_locale.get()`; unchanged behavior when `locale` is omitted.

- [ ] **Step 1: Write the failing test** — create `tests/unit/test_translator_locale.py`:

```python
"""t() honors an explicit locale override, and still falls back to the contextvar."""

from app.core.locale import current_locale
from app.services.translator import load_translations, t


def test_explicit_locale_overrides_contextvar() -> None:
    load_translations()
    token = current_locale.set("vi")
    try:
        # Explicit en wins over the vi contextvar.
        assert t("notification.birthday.title", locale="en") == "Birthday"
        # Omitting locale still uses the contextvar (vi).
        assert t("notification.birthday.title") == "Sinh nhật"
    finally:
        current_locale.reset(token)


def test_unknown_locale_falls_back_to_vi() -> None:
    load_translations()
    # 'de' has no file → fall back to vi text, not the raw key.
    assert t("notification.birthday.title", locale="de") == "Sinh nhật"
```

(These assert the Task-2 keys; run order within the branch is Task 1 then Task 2, so at Step 2 they fail on BOTH the missing `locale` kwarg and the missing keys — that's fine, the decisive RED is the kwarg. After Task 2 they pass.)

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_translator_locale.py -v`
Expected: FAIL — `TypeError: t() got an unexpected keyword argument 'locale'`.

- [ ] **Step 3: Add the `locale` parameter** — in `app/services/translator.py` replace the `t` function with:

```python
def t(key: str, *, locale: str | None = None, **kwargs: object) -> str:
    """Translate a key. Uses ``locale`` when given, else the current request locale.

    Falls back to Vietnamese (vi) if the key is missing in the chosen locale, and
    returns the raw key if missing everywhere. The explicit ``locale`` override exists
    for contexts with no request contextvar (e.g. the notification job sending in each
    recipient's ``user_profiles.language``).

    Usage::

        t("error.member_not_found")                        # request locale
        t("notification.birthday.body", locale="en", name="An")  # explicit locale
    """
    loc = locale or current_locale.get()
    text = _translations.get(loc, {}).get(key) or _translations.get("vi", {}).get(key, key)
    return text.format(**kwargs) if kwargs else text
```

- [ ] **Step 4: Pass locale through in `send_push_notification`** — in `app/services/notification.py`, inside `send_push_notification`, change the two `t(...)` calls that build the message from `t(title_key, **kwargs)` / `t(body_key, **kwargs)` to `t(title_key, locale=locale, **kwargs)` / `t(body_key, locale=locale, **kwargs)` (the function already has a `locale: str = "vi"` parameter).

- [ ] **Step 5: Commit**

```bash
git add app/services/translator.py app/services/notification.py tests/unit/test_translator_locale.py
git commit -m "feat(backend): t() explicit-locale override + per-send locale plumbing (PR-H)"
```

(The test file passes only after Task 2 adds the keys; it is committed here and goes GREEN at Task 2 — acceptable within the branch. If you prefer a green commit now, temporarily assert against an existing key like `t('kinship.child', locale='en')`; either way Task 2 pins the notification keys.)

---

### Task 2: i18n title/body keys (all four locales)

**Files:**
- Modify: `app/i18n/vi.json`, `app/i18n/en.json`, `app/i18n/zh.json`, `app/i18n/fr.json`
- Test: `tests/unit/test_notification_i18n.py` (new)

**Interfaces:**
- Produces: keys `notification.{death_anniversary,birthday,wedding_anniversary}.{title,body}` in all four locales; the flat `notification.<type>` keys removed.

- [ ] **Step 1: Grep-confirm the flat keys have no other consumer**

Run: `grep -rn '"notification\.\(death_anniversary\|birthday\|wedding_anniversary\)"' app/ ; grep -rn 'notification\.\(death_anniversary\|birthday\|wedding_anniversary\)\b' app/ tests/ | grep -v '\.title\|\.body\|i18n/'`
Expected: the only references construct `notification.{event_type}.title`/`.body` (scheduler) — no code reads the flat key. If a flat-key consumer appears, STOP and report.

- [ ] **Step 2: Write the failing test** — create `tests/unit/test_notification_i18n.py`:

```python
"""Every notified event type has a title+body in every locale (not a raw key)."""

import pytest

from app.services.translator import _translations, load_translations

_TYPES = ["death_anniversary", "birthday", "wedding_anniversary"]
_LOCALES = ["vi", "en", "zh", "fr"]


@pytest.mark.parametrize("etype", _TYPES)
@pytest.mark.parametrize("locale", _LOCALES)
def test_title_and_body_exist_in_every_locale(etype: str, locale: str) -> None:
    load_translations()
    table = _translations[locale]
    for suffix in ("title", "body"):
        key = f"notification.{etype}.{suffix}"
        assert table.get(key), f"{locale} missing {key}"


def test_flat_notification_keys_removed() -> None:
    load_translations()
    for etype in _TYPES:
        assert f"notification.{etype}" not in _translations["vi"]
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_notification_i18n.py -v`
Expected: FAIL — the `.title`/`.body` keys don't exist yet (and the flat keys still exist).

- [ ] **Step 4: Edit the four locale files** — in each, replace the three flat `notification.<type>` lines with six `.title`/`.body` lines. Exact content:

`vi.json`:
```json
  "notification.death_anniversary.title": "Ngày giỗ",
  "notification.death_anniversary.body": "Ngày giỗ của {name} còn {days} ngày nữa",
  "notification.birthday.title": "Sinh nhật",
  "notification.birthday.body": "Hôm nay là sinh nhật của {name}",
  "notification.wedding_anniversary.title": "Kỷ niệm ngày cưới",
  "notification.wedding_anniversary.body": "Kỷ niệm ngày cưới của {name} còn {days} ngày nữa",
```
`en.json`:
```json
  "notification.death_anniversary.title": "Death anniversary",
  "notification.death_anniversary.body": "{name}'s death anniversary is in {days} days",
  "notification.birthday.title": "Birthday",
  "notification.birthday.body": "Today is {name}'s birthday",
  "notification.wedding_anniversary.title": "Wedding anniversary",
  "notification.wedding_anniversary.body": "{name}'s wedding anniversary is in {days} days",
```
`zh.json`:
```json
  "notification.death_anniversary.title": "忌日",
  "notification.death_anniversary.body": "{name}的忌日还有{days}天",
  "notification.birthday.title": "生日",
  "notification.birthday.body": "今天是{name}的生日",
  "notification.wedding_anniversary.title": "结婚纪念日",
  "notification.wedding_anniversary.body": "{name}的结婚纪念日还有{days}天",
```
`fr.json`:
```json
  "notification.death_anniversary.title": "Anniversaire de décès",
  "notification.death_anniversary.body": "L'anniversaire de décès de {name} est dans {days} jours",
  "notification.birthday.title": "Anniversaire",
  "notification.birthday.body": "C'est l'anniversaire de {name}",
  "notification.wedding_anniversary.title": "Anniversaire de mariage",
  "notification.wedding_anniversary.body": "L'anniversaire de mariage de {name} est dans {days} jours",
```

Keep each file's existing comma/indent style and valid JSON (the replaced block sits where the three flat keys were).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_notification_i18n.py tests/unit/test_translator_locale.py tests/unit/test_i18n_coverage.py -v`
Expected: PASS (locale parity guard stays green — all four locales gained the same six keys).

- [ ] **Step 6: Commit**

```bash
git add app/i18n/vi.json app/i18n/en.json app/i18n/zh.json app/i18n/fr.json tests/unit/test_notification_i18n.py
git commit -m "feat(backend): notification i18n title/body keys in all locales (PR-H)"
```

---

### Task 3: `send_to_clan` — user_profiles join, off-load, delivery counts, no mid-commit

**Files:**
- Modify: `app/services/notification.py`
- Test: `tests/integration/test_send_to_clan.py` (new); `tests/unit/test_notification_offload.py` (new)

**Interfaces:**
- Consumes: `t(locale=…)` (Task 1).
- Produces: `send_to_clan(...) -> tuple[int, int]` (sent, failed) — Task 4 uses the counts. `send_push_notification` sends via `asyncio.to_thread`. `_remove_invalid_token` no longer commits.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_notification_offload.py`:

```python
"""FCM send is off-loaded to a thread; invalid-token cleanup does not commit."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.notification as notif


@pytest.mark.asyncio
async def test_send_uses_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_to_thread(fn, *a, **k):
        captured["fn"] = fn
        return None

    monkeypatch.setattr(notif.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(notif.messaging, "send", MagicMock(name="send"))
    ok = await notif.send_push_notification("tok", "notification.birthday.title",
                                            "notification.birthday.body", locale="en")
    assert ok is True
    assert captured["fn"] is notif.messaging.send  # the sync SDK call was off-loaded


@pytest.mark.asyncio
async def test_remove_invalid_token_does_not_commit() -> None:
    db = AsyncMock()
    await notif._remove_invalid_token("tok", db)
    db.execute.assert_awaited_once()
    db.commit.assert_not_called()  # must not commit the shared broadcast session
```

Then create `tests/integration/test_send_to_clan.py`:

```python
"""send_to_clan runs against the migrated DB (no auth schema), reads user_profiles.language,
and returns (sent, failed) counts."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import app.services.notification as notif


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_send_to_clan_uses_user_profiles_and_counts(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notif.messaging, "send", MagicMock(name="send"))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
                        {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"})
        await s.execute(sa.text(
            "INSERT INTO user_profiles (id, email, display_name, language) "
            "VALUES (:i, :e, 'U', 'en')"), {"i": user_id, "e": f"u-{user_id.hex[:6]}@x.io"})
        await s.execute(sa.text(
            "INSERT INTO user_clan_roles (clan_id, user_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:c, :u, 'viewer', true, :u, NOW())"), {"c": clan_id, "u": user_id})
        await s.execute(sa.text(
            "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
            "VALUES (:u, :t, 'android')"), {"u": user_id, "t": f"tok-{uuid.uuid4().hex}"})
        await s.commit()

    async with maker() as db:
        sent, failed = await notif.send_to_clan(
            clan_id=clan_id, title_key="notification.birthday.title",
            body_key="notification.birthday.body", db=db, name="An")
    assert (sent, failed) == (1, 0)
    assert notif.messaging.send.called  # no auth.users → no UndefinedTable crash
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_notification_offload.py tests/integration/test_send_to_clan.py -v`
Expected: FAIL — `to_thread` not used (send is called directly); `_remove_invalid_token` calls `commit`; `send_to_clan` returns `None` (not a tuple) and/or the `auth.users` join raises `UndefinedTable` against the migrated DB.

- [ ] **Step 3: Edit `notification.py`** — three changes:

(a) Add `import asyncio` at the top (with the other stdlib imports).

(b) `send_push_notification` — replace `messaging.send(message)` with:
```python
        await asyncio.to_thread(messaging.send, message)
```

(c) `_remove_invalid_token` — delete its `await db.commit()` line (keep the `execute`), and update the docstring:
```python
async def _remove_invalid_token(fcm_token: str, db: AsyncSession | None = None) -> None:
    """Stage removal of an unregistered FCM token. Does NOT commit — the caller's
    transaction (the scheduler's per-event commit) persists it, so this never commits
    a shared broadcast session mid-flight."""
    if db is None:
        return
    await db.execute(
        text("DELETE FROM public.user_fcm_tokens WHERE token = :token"),
        {"token": fcm_token},
    )
```

(d) `send_to_clan` — switch the join to `user_profiles` and return counts. Replace the query + loop with:
```python
async def send_to_clan(
    clan_id: uuid.UUID,
    title_key: str,
    body_key: str,
    db: AsyncSession,
    exclude_user_id: uuid.UUID | None = None,
    **kwargs: Any,
) -> tuple[int, int]:
    """Broadcast to all approved clan members in each member's language.

    Returns (sent, failed) delivery counts. Locale comes from user_profiles.language
    (never auth.users — that schema is Supabase-only and absent locally/in CI)."""
    result = await db.execute(
        text("""
            SELECT ucr.user_id, t.token, t.device_platform,
                   COALESCE(up.language, 'vi') AS locale
            FROM public.user_clan_roles ucr
            JOIN public.user_fcm_tokens t ON t.user_id = ucr.user_id
            LEFT JOIN public.user_profiles up ON up.id = ucr.user_id
            WHERE ucr.clan_id = :clan_id
              AND ucr.is_approved = true
              AND (:exclude IS NULL OR ucr.user_id != :exclude)
        """),
        {"clan_id": clan_id, "exclude": exclude_user_id},
    )
    rows = result.mappings().all()

    sent = 0
    failed = 0
    for row in rows:
        ok = await send_push_notification(
            fcm_token=row["token"],
            title_key=title_key,
            body_key=body_key,
            locale=row["locale"],
            db=db,
            **kwargs,
        )
        sent += 1 if ok else 0
        failed += 0 if ok else 1
    return sent, failed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_notification_offload.py tests/integration/test_send_to_clan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/notification.py tests/unit/test_notification_offload.py tests/integration/test_send_to_clan.py
git commit -m "fix(backend): send_to_clan user_profiles locale + off-load FCM + delivery counts (PR-H)"
```

---

### Task 4: scheduler — lunar exclusion, soft-deleted filter, per-event isolation, truthful log status

**Files:**
- Modify: `app/services/scheduler.py`
- Test: `tests/integration/test_scheduler_robustness.py` (new)

**Interfaces:**
- Consumes: `send_to_clan(...) -> tuple[int,int]` (Task 3).

- [ ] **Step 1: Write the failing tests** — create `tests/integration/test_scheduler_robustness.py`. It reuses the seeding style of `tests/integration/test_scheduler_lock.py` (read that file first). Tests:

```python
"""Scheduler: lunar events excluded, soft-deleted persons skipped, per-event isolation,
truthful log status."""

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import app.core.database  # noqa: F401
from app.services import scheduler


@pytest.fixture()
async def async_engine(migrated_db_url):
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def _seed_event(maker, *, lunar: bool = False, person_deleted: bool = False) -> uuid.UUID:
    clan_id, person_id = uuid.uuid4(), uuid.uuid4()
    event_date = date.today() + timedelta(days=7)
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        await s.execute(sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
                        {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"})
        await s.execute(sa.text(
            "INSERT INTO persons (id, full_name, created_by, is_deleted) "
            "VALUES (:i, 'P', :cb, :d)"), {"i": person_id, "cb": uuid.uuid4(), "d": person_deleted})
        await s.execute(sa.text(
            "INSERT INTO events (id, clan_id, event_type, title, event_date, is_recurring, "
            "is_lunar_calendar, notify_days_before, person_id, created_by) "
            "VALUES (:i,:c,'death_anniversary','Giỗ',:d,true,:lu,7,:p,:cb)"),
            {"i": uuid.uuid4(), "c": clan_id, "d": event_date, "lu": lunar,
             "p": person_id, "cb": uuid.uuid4()})
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_lunar_event_is_excluded(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_event(maker, lunar=True)
    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 0  # lunar event not broadcast


@pytest.mark.asyncio
async def test_soft_deleted_person_is_skipped(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_event(maker, person_deleted=True)
    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 0


@pytest.mark.asyncio
async def test_failed_delivery_logs_failed_status(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    monkeypatch.setattr("app.services.notification.send_to_clan", AsyncMock(return_value=(0, 2)))
    await _seed_event(maker)
    await scheduler.send_anniversary_notifications()
    async with maker() as s:
        status = await s.scalar(sa.text("SELECT status FROM notification_log LIMIT 1"))
    assert status == "failed"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/integration/test_scheduler_robustness.py -v`
Expected: FAIL — lunar/soft-deleted events are still broadcast (spy called); log status is hardcoded `'sent'` (not `'failed'`).

- [ ] **Step 3: Edit `scheduler.py`** — (a) extend the recurring-events query `WHERE` and add the lunar-deferred log; (b) isolate the per-event body; (c) write the real status.

In the query, change the `WHERE` clause and join filter to:
```sql
                    FROM public.events e
                    LEFT JOIN public.persons p ON p.id = e.person_id
                    WHERE e.is_recurring = true
                      AND e.is_lunar_calendar = false
                      AND (e.person_id IS NULL OR p.is_deleted = false)
```

Immediately after `events = result.mappings().all()`, add the deferred-lunar observability log:
```python
            lunar_count = await db.scalar(
                text(
                    "SELECT COUNT(*) FROM public.events "
                    "WHERE is_recurring = true AND is_lunar_calendar = true"
                )
            )
            if lunar_count:
                logger.info(
                    "%s lunar recurring events skipped — lunar support deferred to "
                    "data-model round 2",
                    lunar_count,
                )
```

Replace the `for event in events:` loop body so it is isolated per event and logs the real status. The full loop becomes:
```python
            for event in events:
                try:
                    next_occ = event["next_occurrence"]
                    days_until = (next_occ - today).days
                    if days_until != event["notify_days_before"]:
                        continue

                    dedup = await db.execute(
                        text("""
                            SELECT 1 FROM public.notification_log
                            WHERE event_id = :event_id
                              AND notification_type = :ntype
                              AND DATE(created_at AT TIME ZONE :tz) = :today
                            LIMIT 1
                        """),
                        {"event_id": event["event_id"], "ntype": event["event_type"],
                         "tz": tz_name, "today": today},
                    )
                    if dedup.first():
                        continue

                    sent, failed = await send_to_clan(
                        clan_id=event["clan_id"],
                        title_key=f"notification.{event['event_type']}.title",
                        body_key=f"notification.{event['event_type']}.body",
                        db=db,
                        name=event["person_name"] or event["title"],
                        days=event["notify_days_before"],
                    )
                    status = "sent" if sent > 0 else "failed"
                    error_message = None if sent > 0 else f"0/{sent + failed} delivered"

                    await db.execute(
                        text("""
                            INSERT INTO public.notification_log
                                (clan_id, event_id, user_id, notification_type,
                                 title, body, status, sent_at, error_message)
                            VALUES (:clan_id, :event_id,
                                    '00000000-0000-0000-0000-000000000000',
                                    :ntype, :title, '', :status, NOW(), :error_message)
                        """),
                        {"clan_id": event["clan_id"], "event_id": event["event_id"],
                         "ntype": event["event_type"], "title": event["title"],
                         "status": status, "error_message": error_message},
                    )
                    await db.commit()
                except Exception:
                    # One bad event must not abort the rest of the run. Roll back the
                    # aborted per-event tx so the next event's statements can run.
                    logger.exception(
                        "Notification failed for event %s", event.get("event_id")
                    )
                    await db.rollback()
                    continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_scheduler_robustness.py tests/integration/test_scheduler_lock.py tests/test_notifications.py -v`
Expected: PASS (existing scheduler-lock + notification tests stay green; if `test_notifications.py` mocks `send_to_clan`, its return may now need to be `(1, 0)` — update the mock's `return_value` only, not its intent).

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/integration/test_scheduler_robustness.py
git commit -m "fix(backend): scheduler lunar-exclude + soft-delete filter + per-event isolation + truthful status (PR-H)"
```

---

### Task 5: remove dead `NOTIFICATION_DAYS_BEFORE`

**Files:**
- Modify: `app/core/config.py`, `.env.example`, `backend/CLAUDE.md`

- [ ] **Step 1: Grep-confirm it is unread**

Run: `git grep -n "NOTIFICATION_DAYS_BEFORE" -- backend/app`
Expected: only the definition in `app/core/config.py` (the job uses per-event `notify_days_before`). If any `app/` code reads it, STOP.

- [ ] **Step 2: Remove it**
- `app/core/config.py:70` — delete the line `NOTIFICATION_DAYS_BEFORE: int = 7`.
- `.env.example:27` — delete `NOTIFICATION_DAYS_BEFORE=7 ...`.
- `backend/CLAUDE.md:56` — change `see \`NOTIFICATION_CRON_HOUR\` / \`NOTIFICATION_DAYS_BEFORE\` in \`Settings\`` to `see \`NOTIFICATION_CRON_HOUR\` in \`Settings\``.

- [ ] **Step 3: Full gate**

Run: `./scripts/check.sh`
Expected: `Gate passed.` (config still loads; no reference to the removed setting anywhere).

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py .env.example CLAUDE.md
git commit -m "chore(backend): drop dead NOTIFICATION_DAYS_BEFORE setting (PR-H)"
```

---

## Self-review notes (author)

- **Spec coverage:** S2-2a i18n keys → Task 2; S2-2b per-user locale → Tasks 1+3; S2-5 user_profiles join → Task 3; S2-6 off-load + no mid-commit → Task 3; S2-4 lunar exclude + log → Task 4; S2-3 per-event isolation → Task 4; S2-11 soft-deleted filter → Task 4; S2-9 truthful status → Tasks 3(counts)+4(log); S2-13 dead setting → Task 5. All covered. S2-10 explicitly deferred.
- **Type consistency:** `t(key, *, locale=None, **kwargs)`; `send_to_clan(...) -> tuple[int,int]` produced in Task 3, consumed in Task 4; `send_push_notification(..., locale=...)` unchanged signature, now honored.
- **Not re-doing C2:** lock topology, single `today`, `next_anniversary_sql`, tz untouched — only the query `WHERE`, the loop body, and the log columns change.
- **YAGNI:** no lunar conversion, no S2-10 window change, no durable queue.
