# Backend Scorecard Review — 2026-07-11

Fresh 5-dimension scored review (5 parallel principal-level reviewers, read-only against `main` @ a70cee0),
to decide whether the backend is "grade A / production-ready" enough to start building the frontend.
Supersedes the 2026-07-04 scorecard (`backend-scorecard-review-2026-07-04.md`, ≈7/10) after the merge of
the 3 Critical fixes, seam fixes, PR-J, auth hardening, email verification, and F-1 (API envelope).

## Scores

| Dimension | Score | Grade | vs 2026-07-04 |
|---|---|---|---|
| DB schema & data layer | 8.0 | B+ | ↑ 6.5 |
| Genealogy domain fidelity | 7.0 | C+ | ↑ 6.5 |
| Architecture (DDD/CQRS/hexagonal, SOLID) | 8.5 | B+ | ↑ 8.0 |
| FastAPI / modern Python / API design | 8.0 | B+ | ↑ 7.0 |
| Auth / Supabase / security | 8.5 | A- | ↑ 7.0 |
| **Overall** | **≈8.0** | **B+** | ↑ ~7.0 |

**Unanimous verdict:** every dimension is "proceed with frontend while improving — NOT a blocker." Production
readiness *blockers* (auth trust, clan isolation, config fail-fast, data integrity, stable contract) are done.
The gap to A is a bounded list dominated by **genealogy data-model depth** (the one laggard, and the product core).

## The key finding: freeze contracts, then parallelize

Reviewers independently converged: do NOT build all of grade-A before the frontend. Freeze a few
**load-bearing API contracts** first; then frontend + the remaining backend-A work proceed in parallel,
because everything else lands additively behind stable read shapes.

### 🔒 GATE — freeze BEFORE the frontend binds tree/person/timeline
1. **Structured date representation** — precision enum (exact/year/decade/circa/reign-era) + optional range +
   structured lunar (can-chi). Today: `DATE` + one `_approx` bool + free-text `lunar_*` String(30). Flagged by
   DB *and* genealogy as must-for-A, the #1 retrofit-painful item, and load-bearing for all 3 core screens'
   date inputs. Decide the shape even if the backend fills only exact dates at first.
2. **đa thê child→mother attribution** — `parent_role` on `parent_child` or `via_spouse_id` on child nodes, so
   "con bà cả vs bà hai" renders without reshaping the tree contract later. (Tree currently exposes `children`
   and `spouses` as two disjoint flat lists.)
3. **generation (đời) authority** — compute everywhere (as the tree-focus endpoint does), not the drifting
   hand-entered `clan_memberships.generation` the full-tree endpoint still returns. One authority for "Đời N".
4. **Typed OpenAPI responses** — F-1's `{data}` wrapping dropped `response_model` to opaque `object` on ~79
   routes. Add generic `Envelope[T]`/`Page[T]` `response_model` on fixed-shape routes (document the dynamic
   person reads via `responses=`). **Required before OpenAPI→TypeScript codegen** (standard with Next.js),
   else generated response types are all `unknown`. Request/param types are still typed.

### 🅰 Grade-A backend work (parallel to frontend, additive)
- **Genealogy:** sources/citations layer; person-merge (+ duplicate finder) — the global-person model
  *guarantees* cross-clan duplicates; computed-đời rollout; fix the **`tên huý` name-label bug**
  (`person.py` labels `posthumous_name` as tên huý while domain-rules labels `birth_name` — cheap, do early).
- **DB integrity (cheap, high-value):** `version` optimistic-concurrency column on editable aggregates
  (collaborative editing can silently lose writes without it — trivial now, annoying later); actor-column
  FKs (`created_by`/`updated_by`/`deleted_by`) → `user_profiles` (inconsistent with `identity_claims.reviewed_by`).
- **Architecture:** collapse the **duplicated exception hierarchy** (`ConflictError`/`ForbiddenError` in both
  `domain/shared/exceptions.py` and `core/exceptions.py`; 6 importers; burn the 10-entry import-linter ratchet
  to 0) — the flagship boundary debt; bring the **claims context into the aggregate/event pattern** (currently
  a plain dataclass with `uow: Any` and manual `add_audit`); type `PersonQueryPort` (still `list[dict[str,Any]]`).
- **Auth/API:** close **register email-enumeration** (409 `email_already_exists` leaks existence — inconsistent
  with the non-enumerating reset/verify flows); extend **rate-limit to `/invitations/*/accept`** (token-in-path,
  currently unthrottled).

### ⏸ Explicitly deferred (feature-not-readiness / post-frontend)
- The 5 roadmap features: `change_requests` workflow, `clan_settings` enforcement, audit `ip_address`/`user_agent`,
  field-level visibility, edge cascade-soft-delete.
- Domain tables: tombs/cải-táng, worship-succession (hương hỏa/trưởng tộc), `places`, `person_names` variants,
  polymorphic document attachment + extended doc types (văn bia/gia-phả-scan), `event_participants`.
- **RLS layer-2** — auth reviewer's definitive stance: **NOT a grade-A gate.** App-layer isolation is a
  legitimate primary boundary here — explicit, uniform, provenance-correct, two-sided-tested on real Postgres
  across persons/relationships/tree/timeline/projections/stats. RLS's value is a backstop against a *future*
  dropped predicate, not a present defect. Strongly recommended as defense-in-depth before onboarding many
  clans; groundwork exists (documents pilot + `familyroots_app` NOBYPASSRLS role + GUC default-deny design).
- Ops: Redis-backed rate limiter (multi-replica only); access-token denylist; MFA; GDPR hard-delete.

## Per-dimension highlights

- **DB 8.0** — tenancy model sound + now enforced (per-clan edge uniqueness #007, FK RESTRICT #010, soft-delete
  partial indexes #006, drift gate). Held below A only by domain-completeness (dates, sources, person-merge).
- **Genealogy 7.0** — read/query/presentation layer strong (computed đời, sophisticated kinship resolver,
  path tie-break, đa thê/chi/dâu-rể surfaced). Zero data-model round-2 tables landed → recording capacity for a
  real multi-century clan unchanged. Date model is the hard ceiling. B1 dates / B2 sources / B3 person-merge
  are the must-for-A trio.
- **Architecture 8.5** — boundaries machine-enforced (import-linter 5/5, 0 broken); UoW/event discipline
  airtight; 2 new aggregates. Held below A by the duplicated exception hierarchy + claims-outside-pattern +
  untyped person read side.
- **FastAPI/API 8.0** — async-blocking bug fixed (all SDK calls off-loaded to `to_thread`), envelope uniform,
  excellent error handling/lifespan/config. Held below A by the lost typed OpenAPI response contract (G1) +
  rate-limit scope (G2).
- **Auth 8.5 (A-)** — JWT verification textbook, RBAC re-derived per-request from DB, isolation two-sided-tested,
  email-verification/reset/logout/compensation/PII-redaction all correct. Held below A by register-enumeration
  + app-layer-only-boundary (no RLS backstop).

## Recommendation

1. **Contract-freeze design pass** (the GATE): decide the shapes for structured dates, đa thê child-attribution,
   generation authority, and the typed `Envelope[T]` — a design spec, minimal build. This unblocks frontend.
2. Then **frontend build + grade-A backend work run in parallel**: the cheap high-value backend items
   (name-label fix, `version` column, actor FKs, exception-hierarchy collapse, register-enumeration,
   rate-limit scope) plus the additive genealogy features, sequenced by product priority.
