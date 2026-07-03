# Lessons Learned — Systemic Remediation Series (2026-07-03)

**Context:** Running the stack end-to-end (docker + real Supabase + migrated DB)
surfaced **11+ real bugs that 299 passing tests never caught**. Fixing them
one-by-one would have been whack-a-mole; instead each was traced to a root-cause
*class* and eliminated as a class (PRs A–E: #14 #15 #16 #17 #18). This document
records what we learned, what to do better, and **where similar classes may still
lurk** — the input for the next review round.

> 🇻🇳 **Tóm tắt:** 299 test xanh nhưng chạy thật vẫn lộ 11+ bug. Nguyên nhân chung:
> mọi bug đều nằm ở **đường nối (seam)** mà không tầng test nào đi qua. Bài học lớn
> nhất: *test không thay được việc chạy hệ thống thật*, và guard tốt phải phủ **cả
> lớp bug**, không chỉ con bug. Phần cuối liệt kê các seam còn nghi ngờ — dùng làm
> đề bài cho vòng review tiếp theo.

---

## 1. The core insight: every escaped bug lived in a seam

| Bug (found live) | Seam no test crossed | Why 299 tests were blind |
|---|---|---|
| DI `NameError` on every `/auth/*`, `/me/clans` (#12, #13, PR-A) | FastAPI DI graph | Unit tests construct handlers directly; providers never invoked |
| `row.UserProfileModel` AttributeError → login 500 (PR-B) | ORM `Row` keying | Repos mocked; `Any` typing disabled mypy on the chain |
| DNS failure / wrong API key reported as "invalid credentials" (PR-C) | SDK error mapping | SDK mocked; no test drove a *failing provider* |
| RS256-only verify vs ES256 project → all 401 (PR-C) | JWT signing config | No real token in any test |
| Fresh runtime DB → `relation does not exist` 500s (PR-D) | Runtime environment | Tests migrate their *own* throwaway DB, never the runtime one |
| `uuid = character varying` in stats SQL (#11) | Driver param typing | Repo mocked in unit tests; only real Postgres rejects it |
| CI failures on green local gate (PR-A, PR-E) | Local-gate ↔ CI drift | Local gate ran a *subset* of CI (`ruff format`, `mypy tests/` missing) |

**Rule extracted:** a mock proves your *understanding* of a dependency, not the
dependency. Seams (DI, ORM, SDK, JWT, migrations, CI config) need at least one
test or check that crosses them for real.

## 2. What worked — keep doing

1. **Run the real thing early.** Every docker e2e run surfaced a new seam bug.
   This is now cheap: `docker compose up -d` auto-migrates (PR-D) and the e2e
   battery script exists.
2. **Fix the class, not the instance.** #12/#13 patched missing imports one at a
   time; PR-A removed the pattern that produced them. Same shape for B–E.
3. **Guards that auto-extend.** The DI smoke test *discovers* providers; new
   providers are covered without anyone remembering. Prefer this shape.
4. **Adversarial verification of findings** (2026-06-28 review) and re-verifying
   agent findings against source before acting.
5. **Root-cause investigation before designing the fix** — e.g. proving there was
   *no circular import* before hoisting DI imports; the wrong diagnosis would have
   produced the wrong "long-term" fix.
6. **Decisions recorded where the code is** (port docstrings, UoW docstring,
   ADR updates) — the next reader gets the rule, not just the diff.

## 3. What went wrong in the process — honest list

| Mistake | Cost | Correction now in force |
|---|---|---|
| Declared "login OK" when the 401 was a **masked DNS failure** | Wasted a debugging round; false confidence | Never trust a success-shaped error: verify the *positive* path before interpreting a negative one |
| Local gate ran a subset of CI → 2 CI failures on "green" branches | Red PRs, rework | Gate must mirror CI exactly: `ruff format --check .` + `ruff check .` + `mypy app/ tests/` + `pytest` |
| Chained shell commands masked a ruff exit code (UP031 slipped once) | Late catch | Run gate steps separately; check exit codes explicitly |
| Pushed a commit after the PR was already merged (#10 race) | Hotfix PR #11 needed | Push everything *before* announcing a PR; re-check merge state before follow-up pushes |
| Early doc conclusions from a stale/partial read (RLS "active", ADR-008 "missing", `user_devices` "needs drop") | Corrections mid-review | Verify against migrations/code and the *whole* repo tree before concluding; docs describe intent, not state |

## 4. Suspect seams — where more classes like A–E may hide

Ranked candidates for the **next review round**. Each mirrors an already-proven
failure class.

| # | Seam | Suspicion (same class as) | What to check |
|---|---|---|---|
| S1 | **Storage adapter error handling** (`SupabaseStorageAdapter`) | PR-C taxonomy | `delete()` swallows exceptions; `upload()` errors unclassified. A storage outage during document upload: is the DB row rolled back but the object orphaned (or vice versa)? No compensation path like register's |
| S2 | **Notification / scheduler silent failures** (`services/notification.py`, `scheduler.py`) | PR-C + Theme-E | FCM send errors swallowed by design (ok) — but are *job-level* failures observable? Raw SQL in `send_to_clan` bypasses repos (clan filter discipline?) |
| S3 | **Remaining untyped query ports** (`person_query_port`, `platform_admin`, tree dicts) | PR-B | `dict[str, Any]` shapes — not Row-fragile but mypy-blind; contract drift with schemas possible |
| S4 | **TOCTOU / concurrency** (register slug check-then-insert, invitation accept, rate limiter per-process) | uuid-bindparam class ("only real DB shows it") | Do unique-constraint races surface as 500 instead of 409? Two replicas → in-memory rate limiter is per-pod |
| S5 | **Transaction boundaries in multi-step handlers** (document upload = storage write + DB commit; register = provider + DB with compensation) | PR-D readiness | Partial-failure matrix per multi-system handler: which side can be orphaned? |
| S6 | **In-process event dispatcher coupling** | ADR-004 (accepted-not-built) | Dispatcher re-raise aborts business tx — correct for audit, wrong if notification handlers ever get wired in-tx. The seam invites misuse |
| S7 | **Web/mobile contract drift** (F-1 envelope; response shapes) | PR-B typing | Clients parse mixed shapes; no contract tests between backend and web/mobile |
| S8 | **Hexagonal boundaries enforced by convention only** | PR-A class | One wrong import re-opens the hole; `import-linter` in CI would make the architecture self-enforcing |
| S9 | **E2E is manual** (scratchpad script + live Supabase) | Section 1 conclusion | The most valuable test layer of this session isn't in CI; needs a stubbed-identity HTTP smoke suite or a scheduled e2e job |

## 5. Proposed next steps

1. **Codify the gate** — `backend/scripts/check.sh` mirroring CI exactly (one
   command, fails on first divergence). Cheap, prevents 2 recurred failure modes.
2. **Mechanize the architecture** — add `import-linter` contracts to CI
   (domain imports nothing from app/infrastructure/api; application imports domain
   only; api never imports models/SQLAlchemy). Closes S8 permanently.
3. **HTTP-level auth smoke suite** — TestClient + stubbed IdentityProvider +
   real migrated DB: register→login→me→clans as an *automated* integration test.
   Closes most of S9 without external dependencies.
4. **Next adversarial review round** targeting S1–S7 (the same
   find-then-refute method as 2026-06-28, scoped to these seams).
5. Then resume the **feature roadmap** (change_requests, clan_settings, audit
   IP/device, field-visibility, edge cascade, envelope standardization,
   notifications) on the hardened base.

## 6. Related

- [Backend Design Review 2026-06-28](backend-design-review-2026-06-28.md) — first adversarial audit (Themes A–F)
- [DB Design Review 2026-07-02](db-design-review-2026-07-02.md) — schema/business review + feature roadmap
- Remediation PRs: #14 (DI) · #15 (typed read models) · #16 (auth taxonomy) · #17 (runtime readiness) · #18 (CQRS/tracking)
