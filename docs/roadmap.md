# Roadmap

**What this is:** the one page that answers *"where do I pick up, and what is left?"*
It holds the shape of the work. It deliberately holds no detail — every row links down
to the document that owns it.

**The three planning layers, and which file owns which question:**

| Question | File |
|---|---|
| What is the shape of the whole thing, and what is next? | **this file** |
| What is in flight *right now*, and what is knowingly broken? | [work-register.md](work-register.md) |
| How exactly do I build one thing? | `superpowers/specs/*` (the design) → `superpowers/plans/*` (the tasks) |

Keep this file coarse. When a row's detail changes, the plan changes; when a row's
*state* changes, the work register changes. This page changes only when a stream starts,
finishes, or is re-scoped.

Last updated: 2026-08-02.

---

## 1. Where each stream stands

| Stream | Planned in detail? | Done | Next action |
|---|---|---|---|
| **Web spine** (sub-project A, PR 0) | yes — 13 tasks | Tasks 0–10 | **Task 11** — Playwright + CI |
| **Web feature slices** (PR 1–7) | **no — sketched only** | — | needs a plan per slice |
| **Mobile M0** (spine + login) | yes — 20 tasks | Tasks 1–5 | **Task 6** — Dio interceptors |
| **Mobile M1–M4** | **no — milestones named only** | — | plan after M0 lands |
| **Design system** (sub-project B) | specced, 15 screen groups | spec only | implement inside the slices |
| **Backend** | no active plan | ADR-035 → ADR-039 shipped | driven by client needs + gaps |

---

## 2. Tomorrow: start here

**Web — Task 11 of [`plans/2026-08-02-web-spine.md`](superpowers/plans/2026-08-02-web-spine.md).**
Playwright harness and CI wiring. Two things inside it are load-bearing and easy to skip:
it adds `backend/app/**` to the `api-types-fresh` job's `paths:` trigger — without that
edit the anti-drift gate can never fire on the only case it exists for — and it ships a
`test.fail()` that pins R-lang (work-register §3.1) and turns red the moment that bug is
fixed. Then Task 12 (documentation sync) closes sub-project A's PR 0.

**Mobile — Task 6 of [`plans/2026-08-02-mobile-m0-spine.md`](superpowers/plans/2026-08-02-mobile-m0-spine.md).**
Dio interceptors, then 7–10 (refresh, secure storage, cache, ApiClient). Tasks 11–12
(fonts/theme, l10n) are independent of the network stack and can run in parallel with them.

Both plans are executable as written: every snippet in them was compiled and run before
it was written down, and the defects that found are recorded in each plan's *Verification
status* section.

---

## 3. What still needs planning before it can be built

This is the honest gap. Two streams have a destination but no route.

**Web slices, PR 1–7.** The sequence is fixed in
[`specs/2026-08-02-web-architecture-observability-design.md`](superpowers/specs/2026-08-02-web-architecture-observability-design.md) §5.1
— auth, persons, relationships, tree, events, documents, admin — and each PR migrates its
slice *and deletes the corresponding legacy code*. But only PR 0 (the spine) has a
task-level plan. PR 1 is the natural next planning job, and it carries R-lang.

**Mobile M1–M4.** M1 persons, M2 tree, M3 events + documents, M4 push + admin. Named in
[`specs/2026-08-02-mobile-architecture-design.md`](superpowers/specs/2026-08-02-mobile-architecture-design.md) §6,
no task detail. Plan M1 once M0 proves the spine against the real backend at Task 20.

A stream without a plan is not ready for an implementer agent. Plan first, then build —
the two plans that exist caught real defects precisely because writing them meant running
the code.

---

## 4. Owner actions that block shipped code

Full detail in [work-register.md](work-register.md) §1.2. In one line each:

- **Supabase avatars bucket does not exist** → `set-avatar` returns `503` in every
  environment right now, because ADR-036 is already merged.
- **Supabase email-template link format unknown** → blocks the real verification flow.
  Does *not* block mobile M0.
- **`delete-branch-on-merge` is off** → the remote refills one PR at a time. One click.

---

## 5. Restarting the agent team

Four reusable agent definitions live in [`.claude/agents/`](../.claude/agents/):
`backend-engineer`, `web-engineer`, `flutter-engineer`, `product-designer`. Each carries
this project's gates and guardrails, so a dispatch only needs to say *what*, not *how*.

**Parallel backend agents must each set `TEST_PG_DB_NAME`.** The integration harness
drops its throwaway database `WITH (FORCE)`, so two runs sharing the name drop each
other's — it cost 182 spurious failures in one session. Since 2026-08-03 the name is an
env var (ADR-016), which makes concurrent runs safe *provided each dispatch sets it*; two
agents that both leave it unset still collide on the default. Give every worktree its own
value, e.g. `TEST_PG_DB_NAME=family_roots_schema_test_backend`.

The rules that made parallel work safe, learned the hard way:

- **Agents never push and never open PRs.** They commit to a worktree branch and stop.
  This caught a defect no single agent could see — two backend branches, each green
  alone, red together.
- **Always re-run the gate on the *combined* tree.** Per-branch green proves nothing
  about the composition.
- **Pre-allocate ADR numbers in the dispatch**, or every agent picks the same next free
  number.
- **Fence file territory** when two agents touch adjacent surfaces, and rebase them the
  moment `main` moves underneath.
- **Demand a negative control and re-run it yourself.** Delete the fix, watch the named
  tests fail. Every claim verified this way held; the discipline is why they are
  trustworthy.

---

## 6. Beyond the current streams

Not scheduled, no plan, listed so they are not forgotten:

- **Backend roadmap items** from the 2026-07-02 DB review that remain dormant:
  `clan_settings` enforcement (several knobs inert), audit `ip_address`/`user_agent`,
  field-level visibility, edge cascade-delete on person soft-delete.
- **Change requests beyond `person`-update** — the table already supports marriages,
  parent-child, events and documents with no schema change (ADR-037).
- **Notifications API** — none exists; the design spec refuses to draw a bell for it.
- **PDF export** — deferred by ADR-020, depends on the unbuilt worker (ADR-005) and
  Redis (ADR-004).
- Known gaps and debt: [work-register.md](work-register.md) §3.
