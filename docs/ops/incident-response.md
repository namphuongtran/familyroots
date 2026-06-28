# Incident Response

## Overview
How to triage and respond to production incidents. Single small team — the on-call
engineer owns triage and may escalate to the maintainer for SEV-1.

## Severity levels
| Level | Definition | Examples | Response |
|-------|------------|----------|----------|
| **SEV-1** | Data isolation / auth breach, or data loss | Cross-clan data visible to another clan; auth bypass; destructive migration ran | Immediate: take the affected surface offline if needed, notify maintainer, preserve audit logs |
| **SEV-2** | Core flow broken in production | Login broken, deploy stuck, DB unreachable (`/health` 503), tree/list endpoints 5xx | Same-day: roll back (see `deployment.md`) or forward-fix |
| **SEV-3** | Degraded / partial | Push notifications failing, elevated 4xx, slow queries | Next business day |

## First 15 minutes
1. Confirm scope via `/health` (DB) and Sentry (error rate, the `internal_error` code).
2. Identify the trigger: a deploy/migration (most likely — `main` → prod is direct,
   no staging) or external (Supabase/Render outage).
3. If a recent deploy is implicated → **roll back** (`deployment.md`). If a migration
   shipped, assess reversibility before `alembic downgrade`.
4. For a suspected isolation/auth breach (SEV-1): stop further writes if practical,
   capture `audit_logs` for the window, then patch.

## Known high-severity classes (watch these)
- **Cross-clan access** — isolation is enforced in the app layer (RLS is not yet
  active). A regression in a repository filter or a write-path membership check is a
  SEV-1; the `test_tenant_isolation` / `test_cross_clan_writes` suites guard against it.
- **Migration-blocked deploy** — the Render pre-deploy `alembic upgrade head` blocks
  the release on failure (good), but leaves prod on the old version until fixed.
- **Auth surface** — JWT/JWKS validation and the suspended-clan check gate every
  clan-scoped route.

## Post-incident
- Write a short timeline + root cause; add a regression test (the project's norm is a
  real-DB test per fix).
- If it revealed a design gap, capture it in `docs/decisions/` or the backend design
  review follow-ups.

## Known gaps
- No formal paging/escalation tooling or external status page yet.
- No staging environment to catch issues before production.
