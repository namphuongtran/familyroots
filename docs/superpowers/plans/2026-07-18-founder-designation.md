# Thủy Tổ Founder Designation (A3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `PUT /clans/me/founder` (admin, idempotent designate-or-correct), exactly-one-live-founder DB backstop (migration 023), deterministic `find_clan_founder`, đời activation — closing review finding H3 and flipping the B1 KNOWN_DEFECT pin. Spec: `docs/superpowers/specs/2026-07-18-founder-designation-design.md`.

**Architecture:** Clan aggregate owns designation (route in `api/v1/clans.py`, command/handler in `application/clan/`, `FounderDesignated(AuditableEvent)` via the lightweight `AggregateRoot()` carrier pattern used by `approve_user`). Swap = clear-then-set in one UoW transaction; partial unique index guards out-of-band writers (23505 → existing 409 `conflict`).

**Tech Stack:** FastAPI + SQLAlchemy async, Alembic (raw SQL, `023_one_founder_per_clan`), real-PG integration tests.

## Global Constraints

- Error contract: reuse `person_not_found` (404) for invalid/foreign/deleted target; RBAC 403s come from `RequireClanRole(["admin"])`; index race → existing 23505 → 409 `conflict`. ONE new i18n key `clan.founder_designated` in ALL FOUR locales (`app/i18n/{vi,en,zh,fr}.json` — the i18n coverage test enforces this).
- New route carries documentation-only `responses=ok(FounderDesignationResponse)` (NEVER `response_model=`) + a schema↔body coherence assert in its tests (house pattern).
- Only an admin of the ACTIVE clan may designate; `X-Current-Clan-Id` required (comes free from `get_current_clan_id`).
- Undesignated clan keeps 404 `clan_founder_not_found` on `GET /tree` — that behavior is re-pinned as CORRECT (onboarding state), not removed.
- `clan_memberships.generation` (hand-entered, deprecated) is never touched.
- Migration prechecks fail loudly listing rows (015/021/022 precedent); full downgrade.
- RED-first where behavior changes; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- B1 rate-limit ledger: the designation endpoint is under `/api/v1/clans` — ZERO budget impact; do not change the ledger totals.

---

### Task 1: Endpoint end-to-end (schema → command → handler → repo → route → i18n), RED-first

**Files:**
- Create: `backend/tests/integration/test_founder_designation.py`
- Modify: `backend/app/schemas/clan.py`, `backend/app/application/clan/commands.py`, `backend/app/application/clan/handlers.py`, `backend/app/domain/clan/events.py`, `backend/app/domain/clan/repository.py`, `backend/app/infrastructure/persistence/clan_repository.py`, `backend/app/api/v1/clans.py`, `backend/app/i18n/{vi,en,zh,fr}.json`

**Interfaces:**
- Produces: `PUT /api/v1/clans/me/founder` (body `{"person_id": uuid}` → 200 `{"data": {person_id, previous_person_id, message}}`); repo methods `get_membership_with_person(clan_id, person_id)`, `get_founder_membership(clan_id)`; handler `designate_founder(cmd) -> dict`. Tasks 2–3 rely on these.

- [ ] **Step 1: Write the failing HTTP tests**

Create `backend/tests/integration/test_founder_designation.py` — reuse the RS256/JWKS/client pattern (copy the module fixtures from `tests/integration/test_deactivation_invariant.py`, which is the leanest instance: `rsa_keys`, `jwks_cache`, `_issuer`, `_mint`, `client` overriding ONLY `get_db`, `_sync_engine`, plus seed helpers). Seed via SQL: clan + admin user_profile + approved admin `user_clan_roles` row + persons WITH `clan_memberships` rows (columns: `person_id`, `clan_id`, `role='blood'`, `is_founder` default false — check `app/models/clan_membership.py` for NOT NULLs). Tests:

```python
def _designate(client, token, clan_id, person_id):
    return client.put(
        "/api/v1/clans/me/founder",
        headers={"Authorization": f"Bearer {token}", "X-Current-Clan-Id": str(clan_id)},
        json={"person_id": str(person_id)},
    )


def test_designate_founder_succeeds_and_audits(...):
    # admin + persons A, B seeded
    resp = _designate(client, admin_token, clan, person_a)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["person_id"] == str(person_a)
    assert data["previous_person_id"] is None
    assert data["message"]  # localized, non-empty
    # schema↔body coherence (documentation-only responses= must not drift):
    from app.schemas.clan import FounderDesignationResponse
    FounderDesignationResponse.model_validate(data)
    # DB truth: exactly A is founder
    # audit row exists: action='clan.founder_designate', clan-scoped, actor=admin


def test_correction_swaps_and_reports_previous(...):
    # designate A, then B → previous_person_id == A; DB: only B is founder


def test_idempotent_redesignation(...):
    # designate A twice → second 200, previous_person_id == A, still exactly one founder row


def test_foreign_clan_person_404_two_sided(...):
    # person REAL but belongs to another clan (seed a second clan+person) → 404 person_not_found
    # and the foreign clan's own data is untouched


def test_soft_deleted_person_404(...):
    # seed person with is_deleted=true membership intact → 404 person_not_found


def test_viewer_and_editor_403(...):
    # seed viewer + editor user_clan_roles → 403 insufficient_permissions for both


def test_designation_race_never_two_founders(...):
    # DB-level: two concurrent transactions each do clear-then-set for different
    # persons (raw SQL: UPDATE ... SET is_founder=false WHERE clan_id=:c AND is_founder;
    # then UPDATE ... SET is_founder=true WHERE person_id=:p AND clan_id=:c), gate
    # pattern from test_edge_write_serialization._race. Outcome: at most one "ok"
    # is required to WIN; loser may get 23505 (after Task 2's index) or also
    # succeed serially — the INVARIANT assert is: afterwards the clan has <= 1
    # founder row. Before Task 2's index this test may observe 2 founders → it
    # is EXPECTED RED until Task 2; note it in your report.
```

Write all tests with full bodies (the sketches above name every assertion; flesh them out with the seeding helpers). Run: `uv run pytest tests/integration/test_founder_designation.py -v` → ALL FAIL with 404/405 (route doesn't exist) except possibly the race test (fails on 2-founders). Record output.

- [ ] **Step 2: Schemas** — in `backend/app/schemas/clan.py`:

```python
class FounderDesignationRequest(BaseModel):
    """Body for PUT /clans/me/founder — designate or correct the thủy tổ."""

    person_id: uuid.UUID


class FounderDesignationResponse(BaseModel):
    """Result of a founder designation (ADR-026)."""

    person_id: uuid.UUID
    previous_person_id: uuid.UUID | None = None
    message: str
```

- [ ] **Step 3: Command** — in `backend/app/application/clan/commands.py` (match the file's dataclass style):

```python
@dataclass(frozen=True)
class DesignateFounder:
    clan_id: uuid.UUID
    person_id: uuid.UUID
    actor: ActorInfo
```

- [ ] **Step 4: Event** — in `backend/app/domain/clan/events.py` (mirror `ClanUpdated`):

```python
@dataclass(frozen=True)
class FounderDesignated(AuditableEvent):
    person_id: uuid.UUID | None = None
    previous_person_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "clan.founder_designate")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_membership")
        if self.new_value is None:
            object.__setattr__(
                self,
                "new_value",
                {
                    "person_id": str(self.person_id),
                    "previous_person_id": (
                        str(self.previous_person_id) if self.previous_person_id else None
                    ),
                },
            )
```

- [ ] **Step 5: Repository** — port (`app/domain/clan/repository.py`) + impl (`app/infrastructure/persistence/clan_repository.py`):

```python
# port
    async def get_membership_with_person(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> Any | None:
        """Membership row for a LIVE person of this clan (persons.is_deleted = false)."""
        ...

    async def get_founder_membership(self, clan_id: uuid.UUID) -> Any | None:
        """The clan's current founder membership row, if any."""
        ...

# impl (SqlAlchemy; ClanMembership model import from app.models.clan_membership)
    async def get_membership_with_person(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> ClanMembership | None:
        result = await self._session.execute(
            select(ClanMembership)
            .join(Person, Person.id == ClanMembership.person_id)
            .where(
                ClanMembership.clan_id == clan_id,
                ClanMembership.person_id == person_id,
                Person.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_founder_membership(self, clan_id: uuid.UUID) -> ClanMembership | None:
        result = await self._session.execute(
            select(ClanMembership).where(
                ClanMembership.clan_id == clan_id, ClanMembership.is_founder.is_(True)
            )
        )
        return result.scalars().first()
```

(Adjust the Person import path to `app.models.person`; if `scalar_one_or_none` can see multiple founder rows on legacy data, `scalars().first()` for the founder lookup is deliberate.)

- [ ] **Step 6: Handler** — in `backend/app/application/clan/handlers.py`, mirroring `approve_user`'s carrier pattern:

```python
    async def designate_founder(self, cmd: DesignateFounder) -> dict[str, Any]:
        """Designate or correct the clan's thủy tổ (ADR-026: exactly one live founder).

        Idempotent: re-designating the current founder writes nothing and reports
        previous == person_id. Swap is clear-then-set in THIS one transaction; the
        023 partial unique index backstops out-of-band writers (23505 → 409).
        """
        target = await self._repo.get_membership_with_person(cmd.clan_id, cmd.person_id)
        if target is None:
            raise EntityNotFoundError("person_not_found")

        current = await self._repo.get_founder_membership(cmd.clan_id)
        previous_person_id = current.person_id if current else None
        if current is None or current.person_id != cmd.person_id:
            if current is not None:
                current.is_founder = False
            target.is_founder = True

        agg = AggregateRoot()
        agg.add_event(
            FounderDesignated(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=target.id,
                person_id=cmd.person_id,
                previous_person_id=previous_person_id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {"person_id": cmd.person_id, "previous_person_id": previous_person_id}
```

(Match `AuditableEvent`'s actual constructor fields against `app/domain/shared/events.py` — `approve_user`'s `UserApproved(...)` call is the template; keep whatever base kwargs it uses.)

- [ ] **Step 7: Route** — in `backend/app/api/v1/clans.py`, beside the `/me/users/*` admin actions:

```python
@router.put("/me/founder", responses=ok(FounderDesignationResponse))
async def designate_founder(
    body: FounderDesignationRequest,
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    handler: ClanCommandHandler = Depends(get_clan_command_handler),
) -> dict[str, Any]:
    """Designate or correct the clan's thủy tổ (founder) — roots GET /tree, anchors đời."""
    out = await handler.designate_founder(
        DesignateFounder(
            clan_id=clan_id,
            person_id=body.person_id,
            actor=ActorInfo(user_id=user.id, role="admin"),
        )
    )
    return {
        "data": {
            "person_id": str(out["person_id"]),
            "previous_person_id": (
                str(out["previous_person_id"]) if out["previous_person_id"] else None
            ),
            "message": t("clan.founder_designated"),
        }
    }
```

(Match the file's existing imports/DI names — `get_clan_command_handler`, `ActorInfo` construction style used by the other `/me/users` routes; copy their exact actor pattern.)

- [ ] **Step 8: i18n** — add `"clan.founder_designated"` to all four catalogs (vi: "Đã chỉ định thủy tổ của dòng họ.", en: "Clan founder (thủy tổ) designated.", zh + fr: faithful translations, matching each catalog's tone).

- [ ] **Step 9: Run — endpoint tests green (race test may stay RED until Task 2's index; say so in the report).**
`uv run pytest tests/integration/test_founder_designation.py -v`; then `uv run pytest tests/integration -q` (regression) and mypy/ruff on touched files.

- [ ] **Step 10: Commit**
```bash
git add -A backend/app backend/tests/integration/test_founder_designation.py
git commit -m "feat(clans): PUT /clans/me/founder — designate or correct the thủy tổ (H3, ADR-026)"
```

---

### Task 2: Migration 023 (one live founder per clan) + deterministic find_clan_founder

**Files:**
- Create: `backend/migrations/versions/023_one_founder_per_clan.py`
- Modify: `backend/app/services/tree_builder.py` (`find_clan_founder`)
- Modify: `backend/tests/integration/test_founder_designation.py` (add index sabotage test; the Task-1 race test goes green)

- [ ] **Step 1: Migration** (id `023_one_founder_per_clan`, revises `022_edge_write_serialization`):

```python
_PRECHECK = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.c, '; ') INTO bad FROM (
        SELECT format('clan=%s x%s founders', clan_id, COUNT(*)) AS c
        FROM clan_memberships WHERE is_founder = true
        GROUP BY clan_id HAVING COUNT(*) > 1
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot enforce one-founder-per-clan: %', bad;
    END IF;
END $$;
"""

def upgrade() -> None:
    op.execute(_PRECHECK)
    op.execute(
        "CREATE UNIQUE INDEX uq_clan_memberships_one_founder "
        "ON clan_memberships (clan_id) WHERE is_founder = true"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_clan_memberships_one_founder")
```

Docstring: H3/ADR-026 context, precheck-fails-loud, why partial (`WHERE is_founder`).

- [ ] **Step 2: Deterministic founder read** — in `find_clan_founder` replace the bare `LIMIT 1` query tail with `"ORDER BY cm.joined_at ASC NULLS LAST, cm.person_id LIMIT 1"` and update its docstring (deterministic on legacy multi-founder data; the 023 index makes multiplicity impossible going forward).

- [ ] **Step 3: Sabotage test** (append to test_founder_designation.py):

```python
async def test_second_founder_blocked_at_db(...):
    # designate A via the API, then raw SQL:
    #   UPDATE clan_memberships SET is_founder = true WHERE person_id = :b AND clan_id = :c
    # → expect (DBAPIError|IntegrityError) match "uq_clan_memberships_one_founder"
```

- [ ] **Step 4: Run** — whole file green now (race test included: loser 23505 or serialized, never two founders); migration round-trip (`uv run pytest tests/integration/test_schema_baseline.py -q`); commit:
```bash
git add backend/migrations/versions/023_one_founder_per_clan.py backend/app/services/tree_builder.py backend/tests/integration/test_founder_designation.py
git commit -m "fix(db): one live founder per clan (023) + deterministic find_clan_founder"
```

---

### Task 3: Đời activation proof + flip the B1 pins

**Files:**
- Modify: `backend/tests/integration/test_founder_designation.py` (đời assertions)
- Modify: `backend/tests/integration/test_e2e_journeys.py` (flip H3 pin + Journey 1)

- [ ] **Step 1: Đời proof test** (in test_founder_designation.py): seed a 3-generation family via raw SQL (founder → child → grandchild, biological edges) + designate founder via the API → `GET /api/v1/tree` 200: root id == founder, root `generation == 1`, child 2, grandchild 3, root `is_founder is True`. Also `GET /tree/focus/{grandchild}` → `generation_of_focus == 3`.

- [ ] **Step 2: Flip the H3 pin** in test_e2e_journeys.py:
  - Rename `test_tree_unreachable_for_api_managed_clan_KNOWN_DEFECT_H3` → `test_tree_renders_after_founder_designation`; same setup, then admin designates the created person (`PUT /clans/me/founder`, 0 rate budget), then `GET /tree` → 200, root id == person, `generation == 1`. Docstring: "H3 CLOSED by PR A3; the undesignated-clan 404 remains correct and is pinned separately."
  - Add `test_tree_404_without_founder_designation`: register+login+person, NO designation → 404 `clan_founder_not_found`; docstring marks this the CORRECT onboarding state (client flow: designate → tree renders), citing the frontend-integration-guide section Task 4 adds.
  - NOTE: the H3 flip adds 2 auth-prefix requests (register+login for the new companion test) — recount the module ledger and update the docstring figures.
- [ ] **Step 3: Flip Journey 1's coupled asserts** (the ones the old pin's docstring enumerated): after Stage 5, add designation of ông; Stage 7 asserts flip to `generation_of_focus == 2` (con: ông đời 1 → con đời 2) and ông's ancestors node `generation == 1`. Keep every other exact assert intact.
- [ ] **Step 4: Run both files + full suite; commit:**
```bash
git add backend/tests/integration/test_e2e_journeys.py backend/tests/integration/test_founder_designation.py
git commit -m "test: đời activates — flip KNOWN_DEFECT_H3 to the working tree; pin undesignated 404 as onboarding"
```

---

### Task 4: Docs — contract, guides, ADR-026 (grep-verified)

**Files:**
- Modify: `docs/contracts/rest-clans-api.md` (the new operation: method/path/role/body/response/error cases, idempotency + swap semantics)
- Modify: `docs/contracts/frontend-integration-guide.md` (onboarding flow: undesignated clan → GET /tree 404 `clan_founder_not_found` → admin designates via PUT /clans/me/founder → tree renders; đời now populates)
- Modify: `docs/architecture/tree-read-model.md` + `docs/architecture/domain-rules.md` (thủy tổ designation rule: exactly one live founder, swap endpoint, deterministic legacy read, undesignated = onboarding state)
- Create: `docs/decisions/026-single-founder-designation.md` (format of ADR-025: Context = H3 + nondeterministic find_clan_founder; Decision = admin swap endpoint + partial unique + deterministic ORDER BY; Consequences = đời activates, undesignated-404 is onboarding, soft-deleted founder re-404s until re-designation, export multi-founder tolerance retained for legacy; Alternatives rejected = founder-set management, is_founder on person create)
- Modify: `docs/decisions/README.md` (026 row)

- [ ] **Step 1: Grep sweep first** — `grep -rn "is_founder\|thủy tổ\|thuy-to\|clan_founder_not_found\|founder" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"` — disposition for EVERY hit in the report (update stale "cannot be set via API"-type statements; leave accurate ones).
- [ ] **Step 2: Write the docs above; re-run the grep; zero stale statements.**
- [ ] **Step 3: Commit:** `git commit -m "docs: thủy tổ designation contract + ADR-026; đời activation flow"`

---

### Task 5: Full gate + branch verification (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green. Confirm OpenAPI untyped-2xx sweep still empty (the new route is typed).
