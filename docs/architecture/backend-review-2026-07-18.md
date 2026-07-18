# Backend Deep Review — 2026-07-18 (post-PR #86, main @ e87611d)

Four-agent review (business logic, architecture/design, database, test posture) of the
fully-canonical backend. All High findings were independently re-verified in code by the
coordinator before inclusion. Items already fixed in PRs #72–#86 or explicitly accepted
(in-process events, app-layer RLS, in-memory rate limit) were excluded by construction.

**Verdict:** architecture and DB discipline are strong (clan isolation, OCC, race
backstops, migration hygiene all held up under adversarial scrutiny), but the review
found **5 High** and **~14 Medium** real defects — two of which mean the flagship
graph-computed đời feature cannot activate for API-managed clans at all — plus a test
posture that is excellent at what it covers but blind to several failure classes.

---

## HIGH findings

### H1 — Account deactivation is not an invariant (security)
`is_active` is checked only in `ensure_user_profile` (`app/core/security.py:184`) and
`get_current_clan_id` (`:231`). Every route using bare `get_current_user` skips it:
`POST /invitations/{token}/accept` (`app/api/v1/invitations.py:89-100` — a **deactivated
user becomes an approved clan member**), `POST /auth/onboard`, `POST /auth/login` (issues
tokens + profile), FCM register/remove, `PATCH /auth/me`, `/me/*`. `send_to_clan`
(`app/services/notification.py`) also has no `is_active` filter — deactivated members
keep receiving clan push content.
**Fix:** enforce at one chokepoint (single auth dependency that loads the profile and
gates `is_active`), not three copies; add `is_active` filter to notification fan-out.
Route-matrix test proving every authed route rejects a deactivated user.

### H2 — Acyclicity trigger race: disjoint-endpoint writers can commit a cycle (DB)
`migrations/versions/021_parent_child_guard.py:89-90` serializes via FOR UPDATE on the
two endpoint persons only. Committed edges `D→A`, `B→C`; txn1 inserts `A→B` (locks A,B —
no cycle visible), txn2 concurrently inserts `C→D` (locks C,D — no cycle visible); lock
sets disjoint, both commit → cycle `A→B→C→D→A`. Manual repair; re-running 021's precheck
then fails. Bio-cap check is safe (anchored on the locked child).
**Fix:** `pg_advisory_xact_lock` keyed per clan inside the trigger (genealogy edge-write
rates make per-clan serialization cheap). Real two-transaction race test (pattern exists
in `test_parent_child_db_backstop.py`) proving the hole before, closed after.

### H3 — Thủy tổ (`is_founder`) is unsettable via the API → đời never computes; `GET /tree` 404s
`PersonCreateRequest` has no `is_founder`/`generation`/`membership_role`/`branch_id`
(`app/schemas/person.py` — noted in comment at :230); the only writer is
`application/person/handlers.py:106` from `cmd.is_founder`, which always defaults False;
no membership-update endpoint exists. A clan built entirely through the API:
`find_clan_founder` (`app/services/tree_builder.py:260`) finds nothing → `GET /tree` →
404 `clan_founder_not_found`; every tree/focus/ancestors response carries
`generation: null`; GEDCOM emits no đời notes. Also `find_clan_founder` is `LIMIT 1`
with **no ORDER BY** (nondeterministic root with 2 founder rows) while the export walks
founders deterministically — two authorities that can disagree.
**Fix (needs a small design decision):** founder designation flow — likely
`is_founder` on person create + a membership PATCH (admin) to designate/correct, with
"exactly one founder per clan" or "multi-founder deterministic (earliest joined_at, id)"
semantics decided explicitly; deterministic ORDER BY everywhere.

### H4 — Pedigree collapse: same person gets different đời per endpoint; child dropped from one parent's branch
`get_family_tree_flat` emits one row per lineage path; `tree_builder.py:127-145` dedupes
with last-(deepest)-row-wins and attaches the child to only that parent (`:212-218`).
But `/tree/focus` `_base_generation` (`application/tree/handlers.py:29-44`) and export
`generation_map` (`export_query_port.py:109-110`) take the **shallowest**. A child of
two in-tree parents (marriage within the clan tree — common in real gia phả): `/tree`
says đời 5 and one parent appears childless; `/tree/focus` and export say đời 4.
**Fix:** one authority — min-depth (shallowest) đời everywhere; render the child under
both parents. Decide + document the rule in tree-read-model.md.

### H5 — External HTTP inside open DB transactions; fixed pool → starvation takes down /health (design/scale)
`DocumentCommandHandler.upload` (`application/document/handlers.py:80-111`): SELECT
autobegins a txn, then the Supabase blob upload (seconds for 50MB) runs with that
connection idle-in-transaction, then commit. `ExportQueryHandler._presign_manifest`
(`application/export/handlers.py:120-133`) presigns serially per document holding the
session. Pool hardcoded 10+20 (`core/database.py:20-27`): ~30 concurrent slow
uploads/exports exhaust connections for every endpoint including `/health` (deploy
flapping). Two instances ≈ 62 conns vs Supabase small-tier ~60.
**Fix:** upload blob before opening the write txn (or commit-then-upload with
compensation, matching the purge job's claim ordering); presign after commit /
outside session; make pool env-tunable with documented headroom math; cap or
stream/job-ify export.

---

## MEDIUM findings

- **M1 — Marriage PATCH bypasses `divorce_date ≥ marriage_date`** — validator exists
  only on `MarriageCreateRequest` (`app/schemas/marriage.py:32-38`); update path
  (schema → entity → handler) never re-checks. Divorce dated before the wedding = 200.
- **M2 — Unique backstops narrower than app invariants (race → duplicates)** —
  `idx_marriages_unique_pair` covers only `status='married'` (migration 007) while the
  app treats married/widowed/separated as active (`relationship_repository.py:262-282`):
  concurrent same-pair creates with `widowed` both insert. `idx_parent_child_unique_edge`
  keys on `relationship_type`, app forbids any second live link: concurrent
  `biological`+`step` both insert. Widen partial uniques to match the invariant.
- **M3 — Soft-delete blind spots** — write guards `persons_in_clan`
  (`relationship_repository.py:364-379`) and `person_in_clan`
  (`event_repository.py:47-54`) ignore `is_deleted`: marriages/edges/events creatable
  for a soft-deleted person. `/events/upcoming` joins persons without `p.is_deleted`
  filter (`event_repository.py:90-142`) — deleted persons' giỗ (with names) leak to
  clients while the scheduler correctly suppresses them. `get_birth_dates` same.
- **M4 — Giỗ computed from placeholder dates** — recurring anniversaries feed raw
  `event_date` into anniversary SQL regardless of `precision`
  (`scheduler.py:162`, `event_repository.py:88-146`); a "khoảng 1950" death → clan-wide
  FCM giỗ reminder on the fabricated Jan 1 lunar anniversary, yearly. No guard against
  recurring `death_anniversary` for a person with no `death_date`.
- **M5 — `parent_too_young` hard-422 treats circa as exact** — `get_birth_dates`
  returns no precision (`relationship_repository.py:357-362`); `validator.py:97-117`
  hard-blocks a legitimate lineage on placeholder-date math with no override.
  Precision-aware: hard only when both exact; else `meta.warning`.
- **M6 — GEDCOM invents couples** — >2 parent edges are paired two-at-a-time by UUID
  string order ignoring gender/type/marriage (`gedcom_export.py:172-201`): adoptive
  father + biological father can be emitted as HUSB/WIFE of a FAM that never existed.
- **M7 — `spouse_order` uniqueness only on person1 orientation** — check + index key on
  `person1_id` (`relationship_repository.py:283-306`, migration 015); recording the
  marriage as `(W2, H)` defeats "vợ cả/hai/ba" uniqueness → two wives labeled order 1.
- **M8 — Kinship uses divorced marriages as live spouse edges** — path SQL has no
  status filter (migration 019:82-88); descriptor emits present-tense "Vợ/Chồng",
  "Mẹ kế/Bố dượng" for long-divorced relations (`relationship_descriptor.py:159-264`).
- **M9 — Malformed `?cursor=` → 500 on every paginated endpoint** —
  `decode_cursor`/`decode_fields_cursor` never wrapped (`core/pagination.py`); should
  be 400 `invalid_cursor`.
- **M10 — No DB backstop for cross-clan edges** — parent_child/marriages/events/
  documents FKs don't require same-clan membership; app validates consistently today,
  but one missed validation or raw-SQL job writes a cross-clan edge the tree CTEs will
  traverse. Cheap `clan_memberships`-existence trigger, or explicitly accept.
- **M11 — Expired invitations never transition & permanently block re-inviting** —
  `get_pending_by_email` ignores `expires_at` (`application/invitation/handlers.py:27`),
  partial unique on `status='pending'` blocks re-insert; no cleanup job. Lazy
  expire-on-read + allow re-invite.
- **M12 — Claims audit bypasses the fail-closed dispatcher** — `add_audit` builds
  `AuditLog` directly, no RequestMeta ip/UA (`claim_repository.py:117-140`);
  `cancel_claim` writes audit only `if person:` (`claim_handlers.py:90-101`) — cancel
  can commit with **no audit row**. Route claims through the sanctioned handler.
- **M13 — Post-commit presign failure → 5xx after a successful write** — upload/restore
  call `get_presigned_url` unguarded after commit (`document/handlers.py:124,178`);
  client retry duplicates document+blob (no idempotency key). `set_avatar` (:234-238)
  already has the correct catch-and-None pattern — apply to siblings.
- **M14 — Platform audit list is oldest-first, unindexed platform-wide, unbounded** —
  `paginate_query` hardcodes ASC (`platform_admin_query_port.py:134-151`) though the
  port contract says "recent"; no bare `(created_at)` index; no retention on
  audit_logs/notification_log.

## LOW findings (batched; full details in agent transcripts)

Dual RBAC stacks with divergent semantics (`require_role` vs `RequireClanRole` —
feeds H1; `last_login_at` only on some routes; ORM passed as pydantic type);
ORM rows crossing the hexagon in clan query handlers (`api/v1/clans.py:88-104`);
register compensation ambiguous-commit window (`auth/handlers.py:279-284`);
`uow.track()` dedupes by dataclass value-equality not identity (events silently lost
if two equal-valued instances tracked); invitation tokens stored plaintext (hash them);
scheduler FCM at-least-once across crash+restart within misfire grace;
`display_name` write-once drift after provider rename; `data-model.md` events section
drifted from migration 020 (still says CASCADE, missing soft-delete/version cols);
no CHECK on the five `*_precision` columns; branch hierarchy permits self-parent/cycles
at DB; `clans.founded_year >= 1000` CHECK forbids Lý-era clans; per-clan bio-cap vs
global precheck asymmetry in 021 (install-time vs runtime inconsistency — needs an
explicit decision); trigger fires + locks persons on notes-only edge PATCH
(`_PC_UPDATABLE` always includes trigger columns in SET list); `find_relationship_path`
temp-table churn per call (catalog bloat under frequent kinship lookups);
`PATCH /clans/me/users/{id}/role` takes role as query param (body everywhere else);
documents list re-implements sparse-field filtering inline; `/persons?generation=`
filter + search `generation` serve the deprecated hand-entered column;
scheduler daily queries seq-scan events platform-wide (no leading-column index) and
sentinel `user_id='0000…'` rows drift from documented semantics; unpaginated
invitations list; `tests/test_auth.py` empty TODO stub.

---

## Test posture (map + gaps)

**Current strengths (preserve):** full suite incl. integration runs in CI on real
postgres:18 via the same `scripts/check.sh` as local; genuine two-transaction race
tests with positive AND negative controls; HTTP auth suite verifies real RS256 JWT
against injected JWKS; structural guards (ORM↔schema drift gate, migration round-trip,
i18n coverage sweep, import-linter, N+1 pin, BFS timeout pin); forensic regression
docstrings.

**Ranked gaps:**
1. **Critical — Supabase SDK contract drift invisible**: all GoTrue/Storage behavior
   stubbed or tested against hand-constructed SDK exceptions; SDK change → suite green,
   prod login/upload broken. → opt-in nightly live smoke vs throwaway project, or
   recorded-response contract tests pinned to SDK version.
2. **High — no full HTTP journey; tree routes' DI/serialization seam untested**
   (`/tree`, `/tree/focus` only ever hit with handler mocked; the repo shipped this
   exact bug class twice). → e2e journey suite on migrated DB.
3. **High — check-then-act paths without race tests**: pending-member approval,
   invite-accept vs concurrent removal, registration slug race, concurrent batch.
4. **High — no scale/perf net for tree read model**: nothing beyond 15 hops/50 rows;
   no query-count pin on tree/list routes; pedigree-collapse perf has zero regression
   net. → statement_timeout-pinned 1000-person builds + query-count pins.
5. **Medium-High — FCM + app lifespan never executed** (Firebase init, scheduler start,
   Sentry, startup migration check have no test at all). → lifespan smoke.
6. **Medium** — cursor pagination under concurrent mutation + hostile cursors (ties M9);
   no property-based/fuzz layer (hypothesis for lunar round-trip/HistoricalDate,
   schemathesis vs OpenAPI); OpenAPI declared-schema↔body coherence only asserts $ref
   names on ~25 routes (validate real bodies against components, all-routes sweep);
   mid-flow infra failure injection absent (storage fails after DB commit,
   pg_terminate_backend mid-UoW); residual wall-clock dependence in scheduler/lunar
   tests (inject `today` — pattern exists); shared session-scoped DB creates
   order/parallelism coupling (audit windows, rate-limit budget — not xdist-safe).
7. **Low** — dead/over-mocked legacy tests (delete `tests/test_auth.py` stub, re-scope
   `make_mock_db` tree tests as serialization-only); drift gate blind to
   index/CHECK/type changes; no HTTP i18n assertion (Accept-Language: en / fallback);
   BDD absent — worth pytest-bdd for the 10 owner-reviewable genealogy scenarios only
   if the owner will actually review feature files.

---

## Remediation plan (one PR at a time — see session plan for sequencing)

Track A (fixes, each PR = RED failing test on real PG → fix → full gate):
A1 deactivation invariant (H1) · A2 DB integrity backstops (H2+M2+low CHECKs) ·
A3 founder/đời activation (H3, needs design) · A4 đời single-authority /
pedigree collapse (H4) · A5 soft-delete sweep (M3) · A6 txn/pool hygiene (H5+M13) ·
A7 marriage+precision invariants (M1, M4, M5, M7) · A8 cursor robustness (M9) ·
A9 audit unification + platform audit index/retention (M12, M14) · A10 invitations
lifecycle + token hashing (M11) · A11 GEDCOM/kinship semantics (M6, M8) ·
A12 cross-clan DB backstop decision (M10) · A13 lows batch.

Track B (test strategy buildout, interleaved):
B1 e2e HTTP journey suite · B2 race-pack expansion · B3 perf/scale net ·
B4 property-based + schemathesis · B5 contract-coherence sweep · B6 failure
injection · B7 lifespan smoke + nightly Supabase live smoke · B8 fixture hygiene
(xdist-safe) · B9 BDD scenarios (owner decision).
