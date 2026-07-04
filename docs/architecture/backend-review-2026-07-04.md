# Backend Full Review — 2026-07-04 (layer-by-layer, adversarial)

**Method:** A fresh, whole-backend review requested after the seam-review remediation
(PRs #19–#24) landed. Six finder agents ran in parallel, one per layer — domain,
application, infrastructure/persistence, API, core/middleware/services, models/migrations
— each instructed to *refute* correctness rather than confirm it, to cite `file:line`, and
(for isolation/schema claims) to verify against the live migrated Postgres with read-only
`psql`/`EXPLAIN`. Findings that two independent agents reached (the relationship-validator
clan leak; the document storage ordering) are marked corroborated. Baseline gate was green
before and after: `scripts/check.sh` = ruff format + ruff check + import-linter + mypy(strict)
+ full pytest.

> 🇻🇳 Rà soát toàn bộ backend theo từng lớp (6 tác nhân đối kháng song song, xác minh trên
> Postgres thật). Ba lỗi ưu tiên cao nhất (rò rỉ cách ly dòng họ ở validator quan hệ; xoá/tải
> tài liệu mất-an-toàn trước commit; path traversal qua tên tệp) đã được sửa trong nhánh này.

**Process correction (recorded):** the first pass reviewed a **stale local checkout** — local
`main` was 14 commits behind `origin/main` and did not contain the merged C1/C2/C3 critical
fixes. Those were reported as "still present" in error; a `git fetch` + fast-forward corrected
it. Lesson: always `git fetch` and diff `HEAD..origin/main` before reviewing. The findings
below are against the synced tree (`origin/main` @ PR #24).

---

## 1. Fixed in this branch (`fix/backend-review-clan-isolation-storage`)

### H1 (corroborated: infra + services agents) — relationship-validator reads were not clan-scoped
`RelationshipQueryPort.count_bio_parents` / `has_active_marriage` / `has_parent_child_link`
(`infrastructure/persistence/relationship_repository.py`) filtered only on person ids. Persons
are shared M:N across clans (`clan_memberships`), and edges are owned per-clan
(`created_by_clan_id`), so one clan's marriage / bio-parent / parent-child edges leaked into
another clan's validation — disclosing that the edge exists elsewhere (via the resulting
`duplicate_*` / `too_many_biological_parents` error) and blocking a clan from recording its own
edge for a shared person. Clan isolation is the only enforced tenancy layer (RLS is inert), so
this is a genuine hole.

**Fix:** threaded `clan_id` through the three port methods, their two `RelationshipDomainValidator`
call sites, and both command handlers; each SQL read now carries `AND created_by_clan_id = :clan_id`.
Because the edge-uniqueness indexes were *global* (`idx_marriages_unique_pair`,
`idx_parent_child_unique_edge` keyed only on the person pair — psql-confirmed), scoping the
validator alone would let validation pass and then collide on the index → `IntegrityError` 500.
So **migration `007_clan_scoped_edge_unique`** adds `created_by_clan_id` to both partial unique
indexes, making uniqueness per-clan — matching the confirmed data model (each clan independently
records its own edges for a shared person). Also removed the phantom `uq_parent_child_edge`
`UniqueConstraint` from the `ParentChild` model (finding M8: it didn't exist in the DB and would
make autogenerate recreate a non-partial, non-clan-scoped constraint, reintroducing the 006
soft-delete bug).

**Tests:** `tests/integration/test_relationship_clan_isolation.py` (real migrated DB, two-sided):
a shared child's bio-parent limit counts per clan (clan A hits 2 → blocked; clan B still records
its own; query port returns 2 vs 1 — the negative control that would read 3 if the filter were
dropped); two clans each record the *same* marriage & parent-child edge for shared persons
(exercises migration 007 — a global index would `IntegrityError` here), while within-clan repeats
are still rejected as duplicates.

### H2 (corroborated: application + infra agents) — document storage ordering was unsafe
`application/document/handlers.py`: **delete** removed the blob *before* the DB commit — a
rollback/failure after the storage call left a surviving row pointing at a missing object (every
later download 404s). **Upload** wrote the blob before the commit with no compensation — a failed
commit orphaned the blob. **Fix:** delete is now DB-first (commit the row removal, then best-effort
`storage.delete`, logging an orphan on failure — never a dangling row); upload compensates by
deleting the just-written blob if persistence fails, then re-raising.
**Tests:** `tests/unit/application/test_document_storage_safety.py` — delete ordering
(`repo.delete → commit → storage.delete`), delete durable despite storage failure, upload
compensation deletes exactly the uploaded blob on commit failure.

### H3 — storage path traversal via unsanitized filename
`file_ext = (filename or "file").rsplit(".", 1)[-1]` embedded a client-controlled extension into
the storage key `clans/{clan_id}/documents/...`, whose prefix is the storage tenancy boundary. A
filename like `x.jpg/../../<other_clan>/evil` escaped the prefix. **Fix:** `_safe_extension()`
keeps only lowercase alphanumerics from the last dot-segment (≤10 chars, `bin` fallback), so `/`
and `..` cannot appear. **Tests:** parametrized sanitization + a handler-level assertion that the
storage key stays a fixed 3-level path under `clans/{clan_id}/documents/` with no `..`.

### Already fixed upstream, confirmed
- **M3** (scheduler advisory-lock release on exception) is resolved by the merged **C2** fix
  (`scheduler.py` acquires/releases on a dedicated `engine.connect()` and rolls back before
  unlocking). No further action.

---

## 2. Still open (ranked; recommended next PRs)

### HIGH
- **H4 — `change_requests` UPDATE hard-fails.** `migrations/001` attaches the `updated_at` trigger
  to a table with no `updated_at` column (reproduced live: `record "new" has no field "updated_at"`).
  Latent — the table is dormant — but breaks the moment the D1 change-request workflow is wired.
  Drop the trigger from that table.
- **H5 — person search full seq-scan.** `person_repository.py` filters/sorts on
  `unaccent(lower(full_name))` but the GIN trigram index is on `f_unaccent(full_name)` — expression
  mismatch, index unused (verified via `EXPLAIN`, live search path). Make both sides one canonical
  expression.
- **H6 — `IdentityClaim` raises bare `ValueError` → HTTP 500.** `domain/person/claim_entity.py`;
  only `DomainError` is mapped. Concurrent/duplicate claim transitions surface as 500 instead of
  409/403. Raise `ConflictError`/`ForbiddenError`.
- **H7 — aggregate `update()` blind `setattr`.** `relationship/entities.py` (Marriage/ParentChild)
  and `person/entity.py` accept any key with no whitelist and don't re-check `__post_init__`
  invariants — `update({"person2_id": person1_id})` recreates the forbidden self-marriage;
  `update({"created_by_clan_id": other})` re-points ownership. Add `_UPDATABLE_FIELDS` + re-validate
  (Branch/Event already do this).

### MEDIUM
- **M1** claim approve/prelink TOCTOU → uncaught `IntegrityError` 500 on the `user_profiles.person_id`
  unique constraint (`claim_handlers.py`); `FOR UPDATE` or catch→`ConflictError` + a global
  IntegrityError handler.
- **M2** rate-limiter memory grows unbounded (`core/rate_limit.py` only prunes the current IP).
- **M4** scheduler mixes Python-local `date.today()` with SQL `CURRENT_DATE` under an equality gate,
  and `AsyncIOScheduler`/`CronTrigger` have no timezone → off-by-one *misses* notifications. Pin
  `Asia/Ho_Chi_Minh`, compute the day-delta on one clock. *(Confirmed still present post-C2.)*
- **M5** `clan_settings.max_upload_size_mb` (10 MB) never enforced; domain hard-codes 50 MB.
- **M6** Vietnamese kinship terms ignore gender & birth order (`relationship_descriptor.py` ignores
  `from_gender/to_gender/locale`) — can't render anh/chị/em, chú/bác/cô/dì. Product-correctness.
- **M7** unbounded upload read (`api/v1/documents.py: await file.read()`) before the size check → RAM DoS.
- **M9** `audit_logs.clan_id` FK missing from the model → autogenerate would drop `SET NULL`.
- **M10** clan hard-delete CASCADEs genealogy edges (`created_by_clan_id ondelete=CASCADE`).
- **M11** schema-baseline test only gates table/column add/remove — misses FK/constraint/nullable
  drift (this is *why* M8/M9 shipped). Widen the gated op set. **Highest-leverage systemic fix.**
- **M12** `AuditableEvent.clan_id/actor_id` default to `uuid4()` — fabricates identity if omitted.
- **M13** application layer constructs ORM models + imports Pydantic (boundary leak beyond tolerated
  `app.core` debt).
- **M14** claim isolation keyed on `created_by_clan_id`, not `clan_memberships` (fold into the same
  "one definition of person-in-clan" cleanup as H1).
- **M15** identity `_classify` maps 429/non-auth 4xx to 401 instead of 503.

### LOW
L1 `clans` list `limit` unvalidated (`-5` → 500). L2 JWKS outage → 500 (not 503); rotation → ~1h of
401s. L3 `is_active` never checked in `ensure_user_profile`/`require_role` (latent). L4 read-side
ports return `Any`/`dict`. L5 Person has no `death_date ≥ birth_date` / gender-enum invariant; `create(**kwargs)`
can inject `is_deleted`. L6 parent age-gap (<12y) applied to adoptive/step. L7 dead code
(`core/audit.py` decorator, `services/relationship_validator.py`, empty `api/v1/notifications.py`
stub still mounted). L8 tree-builder no cycle-visited set + drops extra roots. L9 `IdentityClaim`
never sets `reviewed_at`; `reject_as_duplicate` records no reviewer. L10 success-envelope
inconsistency (auth/claims/invitations/platform_admin return bare models). L11 within-clan PII by
default (`GET /persons profile=full`). L12 no `Clan`/`Invitation` domain aggregate. L13 audit
`actor_role` often hardcoded.

---

## 3. Confirmed clean (verified, not assumed)
Layer purity (domain has no framework imports; application has no infra/fastapi imports — now
import-linter-enforced) · UoW commit ordering (flush → collect → dispatch → commit, audit in the
same txn) · **API authz** (every mutating route role-guarded; past claim-route & DELETE-events gaps
fixed; mass-assignment clean; missing-token → 401) · person repo / tree CTEs / mappers / row-key
access all clan-scoped and psql-cleared · config production fail-fast · JWT core (algorithms from
JWKS; aud/iss/exp/signature enforced) · pagination cursor · migration chain linear @ head (now 007).

## 4. Suggested sequence
1. **H4/H5/H6/H7** (live correctness + latent-but-cheap).
2. **M11** (widen schema-baseline drift gate) — prevents the next M8/M9-class escape.
3. **M1 + global IntegrityError handler**, then the M-backlog; several (M5, M14, L11) are on the
   existing DB-review roadmap.
