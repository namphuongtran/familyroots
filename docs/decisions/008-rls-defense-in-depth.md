# ADR-008: Row-Level Security as Defense-in-Depth Layer-2

## Status
Accepted — **Pilot only; not active for application traffic** (as of 2026-06-28).
Shipped: the `documents` pilot (migration `002_rls_documents_pilot`) — a non-bypass
`familyroots_app` role + a fail-closed clan policy, `ENABLE`d (not `FORCE`d), proven
by `test_rls_documents`. Not yet implemented: runtime activation (the app still
connects as a bypass role, so RLS is inert for app traffic), the per-request GUC
plumbing, the role switch, the startup non-bypass assertion, and the table-by-table
rollout + CI coverage test. Until activation, **application-layer isolation is the
only enforced layer**.

## Context
Clan isolation is currently enforced entirely in the **application/repository
layer**: every clan-scoped read takes `clan_id` as a mandatory parameter and
filters on it (clan-owned tables by `clan_id`; relationship edges by
`created_by_clan_id`; persons by a `clan_memberships` join). This layer is
rigorous and covered by two-sided integration tests (a clan sees its own rows;
another clan gets not-found) across every read path.

We want a **second** line of defense at the database boundary so that a future
missed `WHERE clan_id = …` cannot leak cross-clan data. PostgreSQL Row-Level
Security (RLS) is the natural mechanism — but it is **inert** unless the
connecting role is non-superuser and lacks `BYPASSRLS`. Today the backend
connects as a bypassing role (local `postgres`; Supabase service-role), so
simply enabling RLS would be *false security*. Making RLS real therefore
requires a connection-model change and per-request context injection — the
highest-risk change in the production-hardening effort, because a mistake can
make every query return zero rows or error.

The full mechanism, policy SQL, risks, and test plan are in
[the RLS layer-2 design](../superpowers/specs/2026-06-28-rls-layer2-design.md).

> 🇻🇳 **Tóm tắt:** Cô lập dòng họ hiện do **tầng ứng dụng** đảm bảo (mọi truy vấn
> clan-scoped đều lọc `clan_id`, đã test hai chiều). Ta thêm **lớp 2 ở tầng CSDL**
> bằng RLS để phòng trường hợp sau này lỡ quên một bộ lọc. Vướng mắc: backend đang
> kết nối bằng role **bypass RLS** (superuser/service-role) nên bật RLS suông là
> "bảo mật giả". Phải đổi cách kết nối + tiêm ngữ cảnh theo từng request — thay đổi
> rủi ro nhất, nên làm **pilot 1 bảng trước** rồi mở rộng.

## Decision
Adopt RLS as a **defense-in-depth second layer**; the application layer remains
the **primary** isolation mechanism and the source of truth. RLS must never be
the only thing standing between clans.

Implement it as follows (incrementally, pilot-first):

1. **Two connection contexts.** A dedicated non-privileged request role
   (`familyroots_app`, `NOBYPASSRLS`) for the FastAPI request path, under which
   RLS is enforced; and a separate privileged `SYSTEM_DATABASE_URL` for Alembic
   migrations and the cross-clan anniversary scheduler (which legitimately
   bypass RLS).
2. **App-specific GUC context, not Supabase-native.** Inject the active clan/user
   per transaction with `SET LOCAL app.clan_id = …` / `SET LOCAL app.user_id = …`
   and have policies read `current_setting('app.clan_id', true)`. This works
   identically on plain Postgres (local/CI) and Supabase, unlike
   `request.jwt.claims`/`auth.uid()` which require Supabase's `auth` schema.
   `SET LOCAL` is transaction-scoped, so it is pgbouncer-safe and cannot leak
   across pooled clients.
3. **Default-deny.** Policies treat an unset GUC as no access
   (`nullif(current_setting('app.clan_id', true), '')::uuid` → NULL → zero rows),
   so a code path that forgets to set context fails **closed**, never open.
4. **Context injection seam.** A request `ContextVar` (set after
   `get_current_clan_id`/`get_current_user`) drives `SET LOCAL` in the `get_db`
   session — keeping handler signatures unchanged.
5. **Policies mirror the app-layer rules.** Clan-owned tables by `clan_id`;
   edges by `created_by_clan_id`; `persons` via a `clan_memberships` membership
   subquery (M:N).
6. **Pilot-first rollout.** Ship RLS on **one** table (`documents`) plus the
   role, plumbing, and isolation tests as a self-contained first PR; expand
   table-by-table in subsequent, individually-reviewed phases. Each phase is an
   additive migration (role / `ENABLE RLS` / policies) that never touches
   baseline tables, so rollback is `DISABLE ROW LEVEL SECURITY` + drop policies
   (RLS off → the app layer still protects).

## Consequences
Easier:
- A database-level safety net that fails **closed**, catching a future missed
  application-layer filter before it leaks cross-clan data.
- Incremental, low-blast-radius rollout; trivial rollback (disable + drop).

Harder:
- Two connection contexts (request vs system) and the per-request GUC plumbing
  must be maintained; migrations/scheduler must use the system path.
- The `persons` M:N policy uses a per-row subquery — relies on the
  `clan_memberships(person_id, clan_id)` index and needs a performance check.
- New tables must be granted to the request role and given a policy; absence of
  either is a silent gap — guarded by a CI test enumerating RLS coverage.
- A startup/CI assertion is required to prove the request role does not bypass
  RLS (else the whole layer is silently inert).

## Related
- [RLS Layer-2 Design / Spike](../superpowers/specs/2026-06-28-rls-layer2-design.md)
- [ADR-002: Single Schema Clan-Scoped Multitenancy](002-clan-scoped-multitenancy.md)
- [Backend Production Hardening Design](../superpowers/specs/2026-06-27-backend-production-hardening-design.md)
  (SP-2B — application-layer isolation; SP-3C — this RLS layer)
