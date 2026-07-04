# Seam Review Round 2 — 2026-07-04 (S1–S7, adversarial)

**Method:** Phase 2 of [the hardening plan](../plans/2026-07-03-hardening-and-seam-review-plan.md).
One finder agent per seam S1–S7 (from [lessons-learned-2026-07-03](lessons-learned-2026-07-03.md))
read the real code and produced candidate findings with concrete failure scenarios; every
Critical/Important candidate then went to an independent adversarial verifier instructed to
**refute** it (re-reading code, running read-only SQL against the dev Postgres, and executing
non-mutating snippets against the installed dependencies). Only survivors are listed as confirmed.
The verification pass killed or downgraded 8 findings and *sharpened* several others — three
turned out worse than the finder claimed.

> 🇻🇳 Vòng review đối kháng S1–S7: 3 lỗi Nghiêm trọng + 16 lỗi Quan trọng đã xác minh
> (một số chứng minh bằng thực nghiệm trên Postgres). Kế hoạch sửa theo lớp: PR F–K bên dưới.

**Verdict totals:** 3 Critical · 16 Important · ~25 Minor (incl. 8 downgraded by verification).

---

## 1. Critical (confirmed)

### C1 (S5-1) — FCM token writes are never committed; push notifications silently dead
`POST/DELETE /api/v1/auth/me/fcm-token` → `FCMTokenHandler` (no UoW — `dependencies.py:167`)
→ raw `INSERT … ON CONFLICT` on the request session (`auth_repository.py:130-145`). Nothing in
the chain commits: `get_db` only yields (`app/core/database.py:35-38`), no middleware commits.
**Empirically proven** on the dev DB: row visible inside the transaction, **0 rows after session
close** — the pool reset rolls it back. Every client gets a success message; no token is ever
persisted; "removed" tokens keep receiving pushes. Root cause class: *a write path outside the
UoW convention*, invisible because the success response is built from in-session state.

### C2 (S2-1) — One recurring Feb-29 event permanently kills the nightly anniversary job
`scheduler.py:66-77` builds `MAKE_DATE(year, month, day)` from each recurring event's month/day
with no leap guard. **Verified in psql:** `MAKE_DATE(2026,2,29)` errors, and in the simulated
query shape the *entire SELECT* fails — zero events processed for every clan. Worse than found:
in a leap year the ELSE branch computes next year's Feb 29 and errors anyway (job broken ~364
days/year), and after the failure the `finally` unlock raises on the aborted transaction
(`InFailedSqlTransaction`, masking the root error) and **strands the session-level advisory
lock** — empirically shown to make every subsequent run skip with "lock held by another
instance" until the pooled connection dies. The same unguarded `MAKE_DATE` exists in the read
path `event_repository.get_upcoming` (`event_repository.py:86-100`), so the clan's upcoming-events
API breaks too. Feb 29 is creatable today (`schemas/event.py:17`, `is_recurring` defaults True).

### C3 (S4-1) — Invitation accept racing admin revoke silently defeats revocation
Both `accept` and `revoke` check `inv.status != "pending"` on an in-memory snapshot, then issue
unconditional attribute writes (`invitation/handlers.py:79-80,109,131-133`); revoke never touches
`UserClanRole`. Either interleaving ends with the user an **approved member while the invitation
reads "revoked"** (one direction also leaves `accepted_by/accepted_at` populated on a "revoked"
row); both requests succeed. There is **no** `with_for_update`, `version_id_col`, or conditional
UPDATE anywhere in `backend/app` (grep-verified) — an authorization grant that survives explicit
revocation, with invitee-controlled timing.

---

## 2. Important (confirmed)

### Concurrency / commit topology
- **I1 (S4-2)** — Claim approve racing reject/cancel → `user_profiles.person_id` stays linked
  while the claim ends REJECTED/CANCELLED (`claim_handlers.py:121-145,184-221`); the "Race Guard"
  comments are plain SELECTs. No constraint links claim status to the link. Bonus: two concurrent
  approves on the same person → loser hits `uq_user_profiles_person_id` → unhandled 500.
- **I2 (S4-3)** — **No IntegrityError translation exists anywhere** (grep: one `ON CONFLICT`
  upsert, zero catches). Every constraint-backstopped race — clans.slug, user_clan_roles,
  user_profiles.person_id, pending-claim/invitation partial uniques, marriage/parent-child
  partial uniques (all verified present in psql) — surfaces as 500 `internal_error` instead
  of 409. Register's compensation *does* fire on the slug race (provider user deleted), but the
  client still sees 500.
- **I3 (S4-4, sharpened)** — `ensure_user_profile` (`security.py:113-137`): on **read-only
  requests nothing ever commits**, so the lazily-created profile is a *phantom* — created,
  returned, rolled back at teardown, re-created on every GET until the user happens to hit a
  write path. The `last_login_at` refresh flushes an UPDATE that takes a row lock held for the
  whole request → all concurrent requests from one user serialize, always. The SELECT-then-INSERT
  race (loser 500s) is real but narrower — it needs a committing write on the other side. Same
  unguarded pattern in `auth_repository.ensure_profile` and `invitation_repository`.
- **I4 (S4-8, cross-checked via S4)** — clan `approve_user` racing `reject_user` (role row
  deleted) → UPDATE matches 0 rows → `StaleDataError` → 500 (`clan/handlers.py:67-109`).

### Scheduler / notifications (S2 — all six confirmed)
- **I5 (S2-2)** — Pushes render **raw i18n keys**: scheduler asks for
  `notification.{type}.title/.body` but locale files define only flat `notification.{type}`
  (`scheduler.py:108` vs `i18n/vi.json:26`); `t()` falls back to the key string. Additionally the
  per-user `locale` parameter is accepted and **ignored** — `t()` reads the request-scoped
  contextvar, never set in the APScheduler context → everyone gets Vietnamese regardless.
- **I6 (S2-3)** — No per-event error isolation: one bad event aborts the rest of the nightly run;
  the `finally` unlock then raises on the aborted session (`InternalError`/`InFailedSqlTransaction`
  with psycopg — verified), replacing the original traceback; no rollback-before-unlock.
- **I7 (S2-4)** — `events.is_lunar_calendar` is settable end-to-end but **never read** by the
  scheduler or `get_upcoming`: lunar giỗ (the flagship use case; domain-rules.md calls the flag
  "quan trọng với ngày giỗ") are notified on the solar date — wrong day nearly every year.
- **I8 (S2-5)** — `send_to_clan` raw SQL LEFT JOINs `auth.users`, a Supabase-managed schema.
  **Verified absent in the local dev DB** (`to_regclass('auth.users')` → NULL): guaranteed
  `UndefinedTable` crash in every non-Supabase environment, feeding I6's abort-and-mask path.
  Every test mocks `send_to_clan`, so the SQL has never executed in any test.
- **I9 (S2-6)** — `messaging.send` is synchronous (verified: firebase-admin 7.2.0 has no async
  send) and called in the event loop inside the job's open transaction: clan-size × FCM-latency
  event-loop stalls; `_remove_invalid_token` commits the shared scheduler session mid-broadcast.
- **I10 (S5-2)** — The advisory lock is stranded when a mid-job commit releases the connection
  and the unlock runs on a different one — **empirically proven** (lock left held by idle pooled
  pid; unlock returned false). Conditional and self-healing via pool recycle/restart, but it
  silently degrades the single-run guarantee and can suppress a night's run.

### Storage (S1)
- **I11 (S1-1/S1-6/S5-3, adjusted from Critical)** — Document delete is storage-first with the
  adapter swallowing every exception into an ignored `False` (`supabase_adapter.py:31`,
  `document/handlers.py:113-116`): storage outage → row deleted, 200 returned, object orphaned
  *unrecoverably* (the row was the only pointer; no sweeper exists). Privacy angle: the user is
  told it's deleted while already-minted 30-day presigned URLs stay valid. Reverse leg: storage
  delete OK + commit failure → dangling row; every GET then 500s inside presign (verified:
  storage3 raises `StorageApiError`, no handler registered).
- **I12 (S1-3)** — Storage errors are wholly unclassified: `upload`/`get_presigned_url` let raw
  SDK exceptions escape → every storage failure is a generic 500, while the identity seam
  correctly classifies to 503 (`_classify`). Outage vs bug vs config is indistinguishable for
  ops and clients. (`list_documents` doesn't presign, so listing survives — blast radius is
  GET-by-id, upload, set-avatar.)

### Read models / projections (S3)
- **I13 (S3-1)** — `/tree/ancestors` inline recursive SQL fans out on the parent-edge join:
  **reproduced in psql — 7 rows where 5 are correct** (self duplicated at depth 0, each
  two-parent ancestor duplicated per edge; multiplicative along diamonds). The correct
  implementation already exists in the DB (`get_ancestors_flat()`, migration 005, with cycle
  guard) and is used by the relationship path code — the route uses the drifted hand-rolled copy.
- **I14 (S3-3)** — Platform-admin clan detail counts users through `ClanMembership` (a
  Person↔Clan link table): **every clan reports `total_users: 0` until its first person is
  created** (verified: registration writes only Clan + UserClanRole; ClanMembership is created
  only by person_repository). Category error: counting auth users through a genealogy-persons
  table.

### Events / audit (S6)
- **I15 (S6-3, corrected)** — `AuditableEvent.clan_id/actor_id` default to **random UUIDs**
  (`events.py:35-36`, runtime-verified). Corrected split: omitting `clan_id` hits the FK
  (present in migration 001, absent from the ORM model) → loud abort; omitting `actor_id`
  (nullable=False, **no FK** — Supabase-side users) → an audit row silently attributed to a
  random actor, in the table whose purpose is attribution. All 27 current construction sites
  pass both explicitly (latent). Fix verified drop-in on Python 3.14: `kw_only=True`, no defaults.

### Contracts (S7)
- **I16 (S7-2, Critical defensible)** — `/documents` and `/events` return real cursors in
  `meta`, but the web clients type the response as `{data}` only and hardcode
  `has_more: false` (`documents.ts:8-13`, `events.ts:6-12`); the gallery and the **events
  calendar** silently cap at the 20 oldest records. `fetchNextPage` isn't even wired in the
  components. Extra drift: backend meta key is `cursor`; web CLAUDE.md documents `next_cursor`
  — the admin repos (`http-admin-repositories.ts:25,80`) parse `meta` correctly, so the pattern
  exists and simply wasn't applied.
- **I17 (S7-1, adjusted from Critical)** — `GET /persons` never emits a cursor at all
  (`persons.py:135-138`) and the web members list hardcodes the same dead pagination → Members
  page shows exactly 20, with a decoy infinite-scroll sentinel that can never fire. Mitigated to
  Important because `/tree` and search expose all members. Bonus defect: the cursor filter is
  `id > cursor` while ordering by `full_name` — wrong even if wired.
- **I18 (S7-3)** — `platform_role` never reaches any client: not in the UserProfile DTO, not in
  Supabase metadata. A clanless super_admin is funneled into clan-creation onboarding; server
  components detect admin-ness by probing `/platform/metrics` and checking `res.ok`.
- **I19 (S7-4)** — `preferred_locale` round-trip is a lie: PATCH persists it (to Supabase
  metadata only), GET/login always return the schema default `"vi"`; the web then **stomps** the
  correct locally-saved value with "vi" after login (`useAuth.ts:65`), affecting redirects and
  `Accept-Language`.
- **I20 (S7-6)** — The backend's uniform localized error envelope (incl. 503
  `auth_provider_unavailable`, 429) is parsed **nowhere** in web: the `ApiError` type has zero
  importers; the axios interceptor handles only 401; UI catches show axios's generic
  "Request failed with status code N". PR-C's truthful taxonomy never reaches a user.
- **I21 (S7-8)** — `GET /clans/{id}/claims?fields=…` is a guaranteed 500: the route mutates
  `res_dict["claims"]` but the schema field is `items` (`claims.py:62-66` vs `claim.py:45-49`).
  Latent only because the endpoint has zero consumers (see M-group). Also the API's only
  page-numbered, envelope-less list.

---

## 3. Downgraded by verification (were Critical/Important → now Minor)

| ID | Was | Why downgraded |
|----|-----|----------------|
| S1-2 upload compensation gap | Important | Trigger needs a DB fault in a sub-second window after validation; hygiene gap, invisible to users |
| S3-2 /tree/path type drift | Important | Component + hook are dead code — no page renders them (drift is real; fix before wiring) |
| S5-5/S6-6 events drained pre-commit | Important | Only transactional audit handler registered; loss needs a commit-retry that doesn't exist |
| S6-1 dispatcher invites misuse | Important | Abort-on-failure is documented intent (overview.md:96); guardrail gap on a hypothetical register() — but code docstrings do name "notifications" as the example, so fix the docstrings/types |
| S6-2 ADR-004 pre/post-commit mismatch | Important | ADR explicitly unimplemented and itself states the post-commit requirement |
| S7-5 lunar field-name drift (web) | Important | Zero UI touches the fields today; Pydantic silently ignores unknown keys — landmine, fix via contract test |
| S7-7 invitations/claims zero consumers | Important | No creation UI exists either, so no user-facing dead end — dark backend surface |
| S2-1 non-leap-only claim | (correction) | Actually worse: broken in leap years too via the ELSE branch |

## 4. Notable minors (grouped; full details in the fix-class PRs)

- **Storage:** presigned expiry set to *now* instead of now+TTL (S1-4); `set_avatar` gates a pure-DB
  write on a discarded presign (S1-5); dead legacy `services/storage.py` duplicates the swallow
  pattern (S1-7); sync SDK blocks the loop — up to 50 MB per upload (S1-8); unsanitized
  client-controlled file extension lands in the storage path (S1-9).
- **Scheduler:** `notification_log` asserts `status='sent'` even at 100 % failure, `error_message`
  never populated (S2-9); exact-day match drops the year's reminder after one missed run (S2-10);
  soft-deleted persons keep broadcasting (S2-11); dedup test is vacuous — mock indices shifted
  (S2-12); `NOTIFICATION_DAYS_BEFORE` is a dead knob (S2-13); no trigger timezone (S2-8).
- **Read models:** audit log serializes NULL clan_id as `"None"` (S3-4); include sub-query
  exceptions silently become `[]` (S3-5); `events` include token silently unsupported (S3-6);
  divorce never appears on timelines though selected (S3-7); search matches on `birth_name` but
  doesn't return it (S3-8); web sends `max_generations` that the backend ignores (S3-9); both-node
  marriages attach the spouse chip to one side only (S3-10).
- **Concurrency:** marriage unique index predicate (`status='married'`) narrower than the
  validator rule (not-divorced) → widowed/separated duplicates possible (S4-6); rate limiter
  grows unboundedly for one-hit IPs (S4-7).
- **Events:** `track()` dedups by dataclass equality, not identity → equal-valued second instance's
  events silently dropped (S6-4); dispatcher can double-fire a handler registered under related
  types (S6-5); notification code commits caller's session (S6-7).
- **Contracts:** mobile scaffold models pin wrong JSON keys (`name`/`branch`/`profile_image_url`)
  before build-out (S7-9); SSR fetches hardcode `Accept-Language: vi` (S7-10); dead `authApi.login`
  duplicates a contract nobody calls (S7-11).
- **Ratchet burn-down (S3-11):** each of the 7 pinned application→models imports mapped to its
  port abstraction (MembershipRepository shared by 3 sites; claim_handlers → emit_audit_event;
  InvitationRepository.create; ClanRepository.create; ClaimRepository.create_claim).

## 5. Fix-the-class plan (PRs F–K, sequenced)

| PR | Class | Retires | Core change |
|----|-------|---------|-------------|
| **F — Commit integrity** | writes outside UoW | C1, I3 | FCMTokenHandler gets a UoW; `ensure_*_profile` → `ON CONFLICT DO NOTHING` + explicit commit semantics for the read-path dependency (move profile creation off pure reads or commit deliberately); dev-mode teardown assert "no silently-discarded writes" |
| **G — Concurrency + IntegrityError translation** | stale-check-then-write; untranslated 23505 | C3, I1, I2, I4, S4-6 | Conditional `UPDATE … WHERE status='pending'` + rowcount→409 (or `with_for_update`) for invitation/claim/membership transitions; one global IntegrityError handler (23505→409, 23503→404/409) with constraint-name→code table; align marriage index predicate |
| **H — Scheduler/notification robustness** | fragile cron + silent failures | C2, I5–I10, S2-8..13 | Leap-safe occurrence math (shared helper, also in `get_upcoming`); dedicated lock connection (`pg_try_advisory_xact_lock` or pinned conn) + rollback-before-unlock; per-event try/except-continue; fix i18n keys + thread locale through explicitly; read `preferred_locale` from `user_profiles` not `auth.users`; `asyncio.to_thread` for FCM; commit log row before send; truthful send status; lunar decision (exclude-with-doc or convert); integration test that runs the real SQL |
| **I — Storage taxonomy + compensation** | unclassified/swallowed storage errors | I11, I12, S1-4/5/7/8/9 | `StorageUnavailableError/NotFoundError` classification in the adapter + 503 handler (mirror identity `_classify`); DB-first delete with post-commit best-effort storage compensation; upload compensation like register; presign post-commit tolerance + correct expiry; drop dead legacy module; `to_thread` the SDK; whitelist extension from MIME |
| **J — Read-model round 2** | dict-shaped projections | I13, I14, S3-4..11 | `/tree/ancestors` → `get_ancestors_flat()` + frozen `AncestorView`; platform stats via two scalar subqueries + `ClanDetailView`; typed views for audit/timeline; include-token fixes; burn down the ratchet list (start with claim_handlers → emit_audit_event); `AuditableEvent` kw_only (I15, one-line class change verified drop-in) |
| **K — Contract alignment (web-heavy)** | client/backend drift | I16–I21, S7-5/9/10/11 | Backend: emit cursor on /persons (fix filter-vs-order), add `platform_role` + `preferred_locale` to the profile DTO, fix claims `items`/envelope; Web: parse `meta.cursor/has_more` (pattern already in admin repos), envelope-aware axios error normalizer, stop stomping locale, rename lunar fields; add **runtime contract tests** (the existing source-text pin test can't catch any of these) |

Suggested order: **F → G → H → I → J → K** (F and G are small and stop live data-integrity bleeding;
H fixes the only scheduled job; K depends on backend DTO additions landing first).

## 6. Checked clean (selected — full lists in finder transcripts)

- Clan isolation held everywhere audited this round: `send_to_clan` filters approved members per
  clan; scheduler routes strictly by `event.clan_id`; document delete is clan-scoped; no new
  cross-clan leaks found.
- UoW ordering (flush → collect → dispatch → commit) keeps audit rows atomic with business writes;
  single-commit-per-request holds across all command handlers; register compensation is sound and
  correctly fires on IntegrityError.
- JWKS cache stampede-safe; FCM token upsert race-safe (its bug is C1's missing commit, not a race);
  all raw-SQL table names match ORM; tree fixture factories match the SQL function columns exactly
  (no fixture drift); auth/me/tree/relationship/document/event envelopes verified aligned between
  backend and web on 12+ endpoint pairs.
- Dispatcher registry is per-request (no cross-request handler accumulation); exactly one handler
  registered (audit); legacy `@audit` decorator is dead code.

## 7. Related

- [Hardening & seam-review plan](../plans/2026-07-03-hardening-and-seam-review-plan.md) — Phase 2 of this plan; Phase 1 = PR #20
- [Lessons learned 2026-07-03](lessons-learned-2026-07-03.md) — seam catalogue S1–S9
- [Backend design review 2026-06-28](backend-design-review-2026-06-28.md) · [DB design review 2026-07-02](db-design-review-2026-07-02.md)
