# Plan: Process Hardening + Seam Review Round 2 (2026-07-03)

**Goal:** make the design robust long-term — mechanize the guarantees learned from
the remediation series (PRs #14–#18), then hunt the remaining suspected bug
classes (seams S1–S9) with an adversarial review, before resuming features.

**Background:** [lessons-learned-2026-07-03.md](../architecture/lessons-learned-2026-07-03.md)
— 11+ bugs escaped 299 tests; every one lived in a seam no test crossed.

> 🇻🇳 Kế hoạch: (1) cơ khí hoá các bài học (gate script, import-linter, auth smoke
> suite) → (2) vòng review adversarial nhắm các seam còn nghi ngờ S1–S7 → (3) quay
> lại feature roadmap trên nền đã cứng. Quay lại file này để tiếp tục.

## Status

| Phase | Item | Status |
|-------|------|--------|
| 1 | `backend/scripts/check.sh` — local gate mirroring CI exactly | ⬜ not started |
| 1 | `import-linter` contracts in CI (hexagonal boundaries enforced by machine) | ⬜ not started |
| 1 | HTTP-level auth smoke suite (TestClient + stub IdentityProvider + real DB) | ⬜ not started |
| 2 | Adversarial review round 2 targeting seams S1–S7 | ⬜ not started |
| 3 | Feature roadmap (below) on the hardened base | ⬜ blocked on 1–2 |

## Phase 1 — Mechanize the lessons (one PR, "process hardening")

1. **Gate script** `backend/scripts/check.sh`: `ruff format --check .` →
   `ruff check .` → `uv run mypy app/ tests/` → `uv run pytest` — each step
   separate (no chained exit-code masking). CI and humans run the same thing.
   *Accept:* a branch that fails CI must fail this script locally, and vice versa.
2. **import-linter** (dev dep + CI step) with contracts:
   - `app.domain` imports nothing from `app.application/ infrastructure/ api/ models/ schemas` (and no fastapi/sqlalchemy/pydantic);
   - `app.application` may import `app.domain` only (+ schemas per current convention);
   - `app.api` never imports `app.models`/sqlalchemy directly.
   *Accept:* a deliberate bad import fails CI.
3. **Auth smoke suite** `tests/integration/test_auth_http_flow.py`: TestClient +
   stubbed `IdentityProvider` (override the DI provider) + real migrated DB:
   register→login→`/auth/me`→`/me/clans`→create person. Covers the DI graph, the
   envelope, and the read-model mapping over HTTP — the exact layers that hid
   #12/#13. *Accept:* reverting any of those fixes makes it fail.

## Phase 2 — Seam review round 2 (adversarial, find-then-refute)

Scope = S1–S7 from the lessons doc (S8/S9 are closed by Phase 1):

- **S1 Storage adapter**: swallowed errors, no upload compensation (orphaned object vs orphaned row matrix)
- **S2 Notification/scheduler**: silent job failures; raw SQL bypassing repo discipline
- **S3 Untyped query ports**: `dict[str, Any]` shapes in person/platform_admin/tree
- **S4 TOCTOU/concurrency**: slug check-then-insert (500 vs 409), invitation accept race, per-process rate limiter
- **S5 Transaction boundaries**: partial-failure matrix for multi-system handlers (storage+DB, provider+DB)
- **S6 Event dispatcher coupling**: in-tx re-raise semantics vs future notification handlers (ties to ADR-004)
- **S7 Web/mobile contract drift**: envelope inconsistency (F-1), no contract tests

Method: one finder per seam reading real code → adversarial verifier per
Critical/Important finding → fix-the-class PRs like A–E. Record results in a dated
review doc (convention: `docs/architecture/*-review-YYYY-MM-DD.md`).

## Phase 3 — Feature roadmap (after hardening)

From [db-design-review-2026-07-02.md](../architecture/db-design-review-2026-07-02.md) §5:
D1 change_requests workflow · D3 clan_settings enforcement (10 vs 50 MB) ·
D5 audit IP/user-agent (mobile) · E2 person field-visibility (owner-only fields —
open questions: biography? full birth_date?) · E3 cascade soft-delete of edges ·
F-1 `{"data"}` envelope standardization (client-facing!) · F-5 events delete policy ·
F-6 notifications REST surface.

## History (done)

- 2026-06-28: adversarial review #1 (Themes A–F) + hardening phases.
- 2026-07-02: DB design review; isolation/audit/authz fixes (#10 #11); auth e2e fixes (#12 #13).
- 2026-07-03: remediation series — DI (#14), typed read models (#15), auth taxonomy (#16), runtime readiness (#17), CQRS/tracking (#18). All merged.
