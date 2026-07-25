# Claims Audit → Fail-Closed Dispatcher (M12) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** All six claim audit sites route through the fail-closed dispatcher (same-txn + ip/UA enrichment); `cancel_claim` audits unconditionally; the direct `repo.add_audit` writer is removed. Spec: `docs/superpowers/specs/2026-07-25-claims-audit-dispatcher-design.md`. No migration.

**Architecture:** New commit-free `track_audit_event(uow, ...)` in `app/application/shared/audit.py` (buffers a `CrudAuditEvent` on a tracked `AggregateRoot`, no commit — the caller's existing `uow.commit()` dispatches it through `AuditLogHandler`, which enriches ip/user_agent from `RequestMeta`). `emit_audit_event` refactored to `track + commit`. Claims migrate all six `add_audit` calls to `track_audit_event`; `cancel_claim` drops its `if person:` skip; `claim_repository.add_audit` deleted.

**Tech Stack:** SQLAlchemy async, real-PG HTTP-level integration tests (real `RequestMetaMiddleware` populates the ip/UA ContextVar).

## Global Constraints

- **No behavior change to WHAT is audited** — preserve each site's exact `action` / `resource_type` / `resource_id` / `old_value` / `new_value` and actor. Only the write path changes (direct → dispatcher).
- The dispatcher is fail-closed and same-transaction (existing `AuditLogHandler`) — no new dispatcher wiring.
- `track_audit_event` takes `actor: ActorInfo` (mirror `emit_audit_event`); each claim site builds `ActorInfo(user_id=<the id it passes today>, role=<the role string it passes today>)`.
- `AuditLog.clan_id` is nullable → cancel's audit uses `person.created_by_clan_id if person else None`.
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — claims audit rows lack ip/UA (bypass the enriching dispatcher)

**Files:**
- Create: `backend/tests/integration/test_claims_audit.py`

**Interfaces:**
- Consumes: `migrated_db_url`; the claims HTTP endpoints (`POST /persons/{id}/claim`, the admin approve/reject, `POST /claims/{id}/cancel` — grep the claims router + existing claim tests for exact paths + wiring). Drive over HTTP so `RequestMetaMiddleware` sets the ip/user_agent ContextVar.

- [ ] **Step 1: Write the tests** (real HTTP; after each action read the `audit_logs` row for that action and assert ip/UA):

```python
async def test_claim_submit_audit_has_ip_and_user_agent(...):
    # POST /persons/{id}/claim over HTTP (real request → RequestMeta set).
    # SELECT the audit_logs row (action='claim.submit'|whatever the code uses):
    # assert ip_address IS NOT NULL and user_agent IS NOT NULL.
    # RED today: both NULL (claims bypass the enriching dispatcher).

async def test_claim_approve_audit_has_ip_and_user_agent(...):
    # admin approves a pending claim → audit row (action='claim.approve') has ip/UA. RED today.

async def test_claim_cancel_writes_audit_with_ip(...):
    # owner cancels a pending claim → exactly one action='claim.cancel' row EXISTS
    # and has ip/UA. RED today (bypasses dispatcher; also pins cancel audits at all).

async def test_claim_audit_content_preserved(...):
    # a representative action's audit row still has the right
    # action/resource_type/resource_id/old_value/new_value (unchanged by the migration).
```

Discover the exact HTTP paths, the request-meta test setup (how existing HTTP tests get ip/UA populated — `RequestMetaMiddleware` reads the client host / X-Forwarded-For per `RATE_LIMIT_TRUST_FORWARDED_FOR`; TestClient sets a testclient host — confirm ip is non-null for a plain TestClient request, else set an X-Forwarded-For header + the trust flag as existing audit-ip tests do — grep `test_` for ip_address/user_agent audit assertions to mirror the setup EXACTLY). If a plain request yields a null ip in the test env, mirror whatever the existing audit-ip test does to get a non-null ip.

- [ ] **Step 2: Run — record RED.** The ip/UA assertions FAIL today (NULL). If they pass today, STOP → BLOCKED (claims might already enrich — premise wrong).
- [ ] **Step 3: Commit** — `git commit -m "test: RED — claims audit rows lack ip/user_agent (bypass the fail-closed dispatcher) (M12)"`.

---

### Task 2: Route claims audit through the dispatcher

**Files:**
- Modify: `backend/app/application/shared/audit.py` (add `track_audit_event`; refactor `emit_audit_event`)
- Modify: `backend/app/application/person/claim_handlers.py` (6 sites → `track_audit_event`; cancel unconditional)
- Modify: `backend/app/infrastructure/persistence/claim_repository.py` (delete `add_audit`)

- [ ] **Step 1: shared/audit.py** — split out the buffer step:

```python
def track_audit_event(
    uow: UnitOfWork,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    actor: ActorInfo,
    clan_id: uuid.UUID | None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    """Buffer a CrudAuditEvent on a tracked aggregate WITHOUT committing — the
    caller commits (dispatching it through the fail-closed AuditLogHandler, which
    enriches ip/user_agent from RequestMeta) as part of its own write txn."""
    agg = AggregateRoot()
    agg.add_event(
        CrudAuditEvent(
            action=action, resource_type=resource_type, resource_id=resource_id,
            clan_id=clan_id, actor_id=actor.user_id, actor_role=actor.role,
            old_value=old_value, new_value=new_value,
        )
    )
    uow.track(agg)


async def emit_audit_event(uow, *, action, resource_type, resource_id, actor, clan_id,
                           old_value=None, new_value=None) -> None:
    track_audit_event(uow, action=action, resource_type=resource_type,
                      resource_id=resource_id, actor=actor, clan_id=clan_id,
                      old_value=old_value, new_value=new_value)
    await uow.commit()
```

(Note `clan_id` becomes `uuid.UUID | None` — `emit_audit_event`'s existing callers pass a non-None clan_id, unaffected. Verify their call sites still type-check.)

- [ ] **Step 2: claim_handlers.py** — at each of the 6 `self._repo.add_audit(...)` sites, replace with:

```python
        track_audit_event(
            self._uow,
            action=<same>, resource_type=<same>, resource_id=<same>,
            actor=ActorInfo(user_id=<the id passed today>, role=<the role passed today>),
            clan_id=<same>,
            old_value=<same>, new_value=<same>,
        )
```

Import `track_audit_event` (from `app.application.shared.audit`) and `ActorInfo` (from `app.domain.shared.value_objects`). Keep the existing `await self._uow.commit()` after each. **cancel_claim**: remove the `if person:` guard — `person = await self._repo.get_person(claim.person_id)`, then `clan_id = person.created_by_clan_id if person else None`, then `track_audit_event(...)` unconditionally.

- [ ] **Step 3: claim_repository.py** — delete `add_audit`; remove the now-unused `AuditLog` import if nothing else in the file uses it (ruff/mypy will confirm).
- [ ] **Step 4: Run** — Task-1 file green (ip/UA now populated); existing claims + audit suites green; FULL suite (report count). mypy: check per-module overrides. If an existing test asserted `add_audit` was called (mock), update to assert the dispatched audit row instead — justify.
- [ ] **Step 5: Commit** — `git commit -m "fix(claims): route audit through the fail-closed dispatcher (+ip/UA); cancel audits unconditionally; drop direct add_audit (M12)"`.

---

### Task 3: Docs (grep-verified)

**Files:**
- Modify: `docs/architecture/backend-developer-guide.md` (audit section) — or the doc that describes the audit/event dispatcher.

- [ ] **Step 1: Grep** — `grep -rn "add_audit\|audit\|fail-closed\|dispatcher\|ip_address" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"`. Disposition each.
- [ ] **Step 2: Edit** — the audit-writer description: the fail-closed dispatcher (`emit_audit_event` / `track_audit_event` → `AuditLogHandler`) is now the ONLY audit writer; claims were the last direct writer (`add_audit`) and now route through it, gaining ip/user_agent enrichment. Any doc claiming claims audit differently → corrected.
- [ ] **Step 3: Re-run grep; zero stale statements. Commit** — `git commit -m "docs: claims audit routes through the fail-closed dispatcher (M12)"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
