# Backend Scorecard Review — 2026-07-04 (5 dimensions, owner-requested)

**Method:** Owner asked for a thorough, layer-by-layer assessment answering "is the
backend good enough to build a real multi-generational Vietnamese clan-genealogy
system?" — with a score per dimension. Five specialist reviewer agents ran in
parallel, one per dimension, each read-only against the synced tree, citing
`file:line`, verifying schema/isolation claims against the live migrated Postgres,
and returning STRENGTHS / GAPS / SCORE(/10) / recommendations.

This is a **completeness & fitness** review (is the design rich and correct enough
for the domain, and modern/idiomatic enough to build on). It complements — does not
replace — the **correctness/seam** reviews:
[backend-review-2026-07-04](backend-review-2026-07-04.md) (layer-by-layer, adversarial),
[seam-review-2026-07-04](seam-review-2026-07-04.md) (S1–S7),
[db-design-review-2026-07-02](db-design-review-2026-07-02.md).

> 🇻🇳 Đánh giá backend theo 5 khía cạnh, có điểm số, trả lời "đã đủ tốt để làm hệ
> quản lý gia phả dòng họ nhiều đời chưa?". Kết luận: **nền kỹ thuật đủ tốt để xây
> tiếp (kiến trúc 8/10); nhưng mô hình dữ liệu chưa đủ giàu cho gia phả hàng thế kỷ
> (DB 6.5, độ sát thực tế 6.5)** — cần "vòng thiết kế dữ liệu 2".

---

## Scorecard

| # | Dimension | Score | One-line |
|---|-----------|:-----:|----------|
| 1 | Database schema design (tables, relationships, constraints) | **6.5/10** | Relational core excellent; domain completeness for multi-century genealogy is the gap |
| 2 | Real-world Vietnamese-genealogy fidelity | **6.5/10** | Great for a *living* clan; strains on a real *centuries-old* gia phả |
| 3 | Architecture / DDD-CQRS-hexagonal / SOLID | **8.0/10** | Strongest dimension — boundaries machine-enforced (import-linter) |
| 4 | FastAPI / async / SQLAlchemy 2 / Pydantic v2 | **7.0/10** | Modern foundation; blocking sync I/O + untyped responses hold it back |
| 5 | Auth / Supabase (correctness + security + usability) | **7.0/10** | Validation/RBAC strong; missing product-table-stakes flows |
| | **Weighted overall** | **≈ 7.0/10** | Engineering foundation solid; data-model completeness is the work ahead |

**Verdict — "đã đủ tốt để implement backend chưa?"**
- **Engineering/architecture: YES**, good enough to keep building on (8/10; hexagonal boundaries CI-enforced; the correctness/security seams from prior reviews are fixed).
- **Genealogy data model: NOT YET** for the flagship use case (entering a real, uncertain, multi-century gia phả). Needs a "data-model round 2" (§4) before onboarding clans with deep historical records.

Weights used: DB 25% · genealogy 20% · architecture 25% · FastAPI 15% · auth 15%
(reflecting the owner's stated primary focus on data design + the domain).

---

## 1. Database schema design — 6.5/10

**Strengths:** global-person + `clan_memberships` M:N tenancy (a shared ancestor/in-law in
many clans — the hard part, done right); edges (`marriages`/`parent_child`) global but
clan-scoped-unique + soft-delete-aware partial indexes (migrations 006/007); deliberate,
hardened FK on-delete (edges RESTRICT, migration 010); Vietnamese diacritic-insensitive
search (GIN + trigram); đa thê via `spouse_order`, no hard limit; solid CHECK/constraint set.

**Top gaps (missing tables/columns):**
- 🔴 **Date model can't record old dates** — `DATE` + one `_approx` boolean can't store
  "circa 1750", year-only, decade, or reign-era; `lunar_*` are just `String(30)` labels. The
  single biggest fitness gap vs "many generations/centuries."
- 🔴 **No sources/citations layer** — no way to attach evidence/confidence to a fact or record
  conflicting sources. The defining feature of serious genealogy.
- 🟠 **Places are free-text** (~10 scattered columns) → need a hierarchical `places` table with
  historical name variants (VN place names change constantly).
- 🟠 **Names are fixed columns** → need a `person_names` table (tên huý/tự/thụy/hiệu, type +
  period + source). *Doc/model conflict:* `person.py:33` labels `posthumous_name` "tên huý" while
  `domain-rules.md` labels `birth_name` "tên huý".
- 🟠 **No person-merge / redirect** (`person_merges`) — the multi-clan model guarantees duplicates.
- 🟡 Missing: `version` (optimistic concurrency); FK on actor columns (`created_by`/`updated_by`/
  `deleted_by`/`actor_id`) → `user_profiles` (inconsistent: `identity_claims.reviewed_by` *has* it);
  `event_participants` (multi-person events); `restored_at/by` + cascade-delete linkage;
  index `(child_id, created_by_clan_id) WHERE is_deleted=false` for ancestor traversal.

## 2. Real-world genealogy fidelity — 6.5/10

**Strengths:** đa thê with per-mother child attribution; bio/step/adopted/foster edges (age-gap
floor correctly bio-only); full Vietnamese name set; lunar giỗ; chi/phái self-referential
hierarchy; a genuinely sophisticated kinship resolver (nội/ngoại by linking-parent gender,
relative age, disciplined "don't guess" fallbacks); correct cross-clan row-level in-law visibility.

**Top missing scenarios (frequency × severity):**
- 🔴 **"Đời thứ mấy" is hand-entered, not computed** (`clan_memberships.generation`) — the
  most-asked gia phả question can't be answered reliably; drifts when ancestors are inserted.
  → compute via recursive distance from the founder.
- 🔴 **No person merge / duplicate detection** — the load-bearing promise of the global-person
  model; without it trees fork per-clan.
- 🔴 **No source/evidence/confidence** (mirrors §1) — centuries-old lineage from conflicting
  sources is all asserted as fact.
- 🟠 Uncertain "circa/era/range" dates; **worship succession (hương hỏa / trưởng tộc)** and
  từ đường/phần mộ not first-class; **cải táng** has no event type; half- vs full-siblings not
  distinguished (single shortest path); married-in in-law's natal lineage not linkable
  (`change_requests` dormant); **no GEDCOM/paper-gia-phả import**.

*Two independent domain reviewers converged on the same list — high confidence.*

## 3. Architecture / SOLID — 8.0/10 (strongest)

**Strengths:** import-linter runs live **5/5 contracts PASS** — hexagonal boundaries are now
*machine-enforced* (closes seam S8 permanently); domain layer framework-pure; DIP restored (every
handler types its UoW as the domain port); the audit-drop bug class eliminated at the repository
seam (fix-the-class, not per-handler); Repository/UoW/domain-events/composition-root all correct.

**Weaknesses (tech debt, not defects):**
- 🟠 **Duplicated exception hierarchy with colliding names** — `ConflictError`/`ForbiddenError`
  exist in *both* `domain.shared.exceptions` (pure) and `core.exceptions` (HTTPException
  subclasses); 4 handlers still use the core ones.
- 🟠 **Claims context sits outside the architecture** — `IdentityClaim` is not an `AggregateRoot`,
  UoW typed `Any`, audit written manually (the pattern the audit-seam fix eliminated elsewhere).
- 🟠 **`app/services/*` split-brain** incl. dead `services/storage.py` (0 importers) shadowing the
  real adapter; untyped mypy island.
- 🟡 Residual `dict[str,Any]` query ports (person); `persons.py` (500 lines / 14 routes) is the
  SRP/coupling hotspot.

## 4. FastAPI / modern techniques — 7.0/10

**Strengths:** `lifespan` (not deprecated `on_event`); uniform `{error:{code,message,detail}}`
envelope with MRO-aware handlers; SQLAlchemy 2 `Mapped`/async + `pool_pre_ping`; pydantic-settings
v2 fail-fast; cursor pagination; CI-mirror gate + real migrated-Postgres integration tests;
structured JSON logging + Sentry + real `/health` readiness.

**Gaps / outdated:**
- 🔴 **Blocking sync I/O in `async def`** — Supabase Storage SDK and `firebase_admin.messaging.send`
  called inline in async, freezing the event loop per upload/push. → `asyncio.to_thread` or async
  clients.
- 🟠 **No `Annotated[T, Depends(...)]`** (B008 silenced instead of adopting the idiom).
- 🟠 **66/77 routes return `dict[str,Any]` with no `response_model`** → OpenAPI describes most of
  the API as opaque dicts.
- 🟡 In-memory rate limiter is single-replica-only (needs a startup guard or Redis before scale-out).

## 5. Auth / Supabase — 7.0/10

**Strengths:** JWKS-derived algorithm allowlist (no alg-confusion); truthful 401/503/422 taxonomy;
thread-safe JWKS cache; RBAC re-derived per-request from `user_clan_roles` (user+clan, `is_approved`);
super-admin DB-sourced not JWT-sourced; register all-or-nothing (compensating Supabase delete);
clan-switcher UX; config fail-fast with no secret leakage; honest RLS-is-inert documentation.

**Gaps / risks:**
- 🔴 **A1 — `ensure_user_profile` had C1's twin bug** (uncommitted lazy write → phantom profile on
  read-only requests). **FIXED — PR #58** (ON CONFLICT upsert + commit + re-select; closes the
  concurrent-first-login race too; concurrent test empirically discriminated).
- 🟠 Missing product table-stakes: **password reset**, **email verification** (`email_confirm=True`
  unconditionally → register under someone else's email), **MFA**, **account deletion (GDPR)**.
- 🟡 `PATCH /me` updates Supabase metadata only, not the local DB; `GET /me` reads name from the JWT
  → profile edits invisible until token refresh.

---

## Documents / media — can it hold clan "dấu tích / bút tích"? (owner question)

**Yes for basic per-person upload:** `documents` supports photo/id_document/certificate/audio/video
on Supabase Storage (≤50MB CHECK, MIME check, avatar, taken_date/place), clan-path-isolated.

**Gaps for clan-level relics/handwriting:**
- Attaches to `person_id` only — **not** to a clan, branch (chi/phái), marriage, parent_child edge,
  or event; a scan of the whole gia phả book / văn bia / gia huấn manuscript has no proper home.
- `document_type` enum lacks manuscript / văn bia / gia-phả-scan / bút tích.
- No tie to a sources/citations layer, so a document can't act as **evidence** for a fact.
→ Fold into the data-model round 2 as **polymorphic document attachment** + extended types + citation link.

---

## Consolidated: tables / modules to add (beyond tracked roadmap D1–E3)

**New tables:** `sources` + `citations` · `places` · `person_names` · `person_merges` ·
`event_participants` (or `facts`) · `tombs` (incl. cải táng) · `import_batches` · worship-succession.
**Column/model changes:** date-precision + range + structured lunar (persons + events) ·
`parent_role` (father/mother) on `parent_child` · `version` (optimistic concurrency) ·
FK actor columns → `user_profiles` · `restored_at/by` + cascade-delete linkage ·
computed `generation` (đời) · ancestor-traversal index · polymorphic document attachment + doc types.
**Modules/features:** person-merge command + duplicate finder · cross-clan link workflow (activate
`change_requests` / D1) · GEDCOM/paper import pipeline · password reset + email verification + MFA +
account deletion · async offload for blocking SDK calls.

## Recommended sequencing

1. **A1 fixed** (PR #58) — commit-integrity twin of C1. ✅
2. **Data-model round 2** (this doc §"Consolidated") — the owner's primary concern; do a design +
   plan pass first (dates, sources/citations, person-merge, computed generation, names/places,
   worship, polymorphic documents), then migrations + code per feature.
3. Remaining Important seam-fixes (PRs G/H/I/J/K proper — see
   [seam-review-2026-07-04 §5](seam-review-2026-07-04.md)).
4. Product-completeness auth flows (password reset, email verification, MFA, account deletion).
5. FastAPI hygiene sweep (async offload, response models, `Annotated` deps, rate-limit guard).

## Related

- [backend-review-2026-07-04](backend-review-2026-07-04.md) — layer-by-layer correctness review (companion)
- [seam-review-2026-07-04](seam-review-2026-07-04.md) · [db-design-review-2026-07-02](db-design-review-2026-07-02.md)
- [lessons-learned-2026-07-03](lessons-learned-2026-07-03.md) · [overview](overview.md) · [data-model](data-model.md)
