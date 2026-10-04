# Roadmap

**What to build first, and why.** This file holds the **milestone order** and the reason for each
boundary. It holds no work. What is scheduled today lives in GitHub Issues on
`namphuongtran/familyroots`, which is the only tracker.

**Rewritten 2026-08-13.** It held a status board until then, alongside a second state file,
`work-register.md`. Two places recording the same state is two places to be wrong, and both went
stale: on 2026-08-13 this file still listed audit `ip_address`/`user_agent` as dormant work when
`backend/app/models/audit_log.py:36-37` had already declared both columns.

**The list that started all of this is gone, and it went in that same rewrite.** Section 6,
"Beyond the current streams", held four dormant items from the 2026-07-02 database review at
lines 125 to 129. Commit `53f121d` deleted the whole section on 2026-08-13. Verified on 2026-08-22:
`git show 53f121d^:docs/roadmap.md | sed -n '118,135p'` prints the section, and no line of this file
names an item of that list any more. Every remaining mention here describes the list rather than
being it.

**This file decides nothing, and three of the boundaries below rest on no source.** Where that is
true it says so. A boundary marked "not verified" is the maintainer's order and is real; what is
missing is a written reason, and writing one is a decision that would get an ADR.

## The target

**One real Vietnamese clan uses the web app for real data.** Chosen by the maintainer on 2026-08-13.
Mobile M1 through M4 lands after that, and only mobile's device-walk unblock is on the critical path.

That target is what orders the milestones below. A different target reorders them: shipping both
clients together would put mobile M1 alongside the web slices and add store-release work, and a
dogfood-only target would drop the polish and keep the isolation and backup work.

## The order, and what each step rests on

| Step | Because | Read |
|---|---|---|
| **M0** first: make the surface verifiable — **its token reason discharged 2026-08-13** | "Until the semantic tokens resolve, nothing else can be verified on screen." **They resolve now.** Until 2026-08-13 the browser dropped seventeen semantic colour tokens, because `@theme` wrapped hex strings in `hsl()`. They hold literal values today (`web/src/app/globals.css:19-219`), including `--color-secondary` and `--color-secondary-foreground` at `:126-127`, which had never been defined. `web/src/app/theme-tokens.test.ts` has gated them since 2026-08-22. Read on 2026-10-04 in #166: its 174 cases pass, and planting the original `hsl(#7a6248)` on `--color-secondary` fails the case named for that token. **M0 has one item left**, the 200%-text-scale defect on the backoffice, pinned red at `web/e2e/auth/backoffice.auth.spec.ts:154` and filed as #174 and #175 | [design spec § 2.8.1](superpowers/specs/2026-08-02-design-system-and-screens.md), line 400 for the ordering, and [`../.claude/rules/tailwind.md`](../.claude/rules/tailwind.md) § 2 for the fix and its gate |
| **M1** runs alongside **M2**, and closes before the first real clan's data | Clan isolation is the one defect that cannot ship, and the root `CLAUDE.md:29` forbids bypassing it. It is ordered against the target above, real data, not against screens. **The old "before M2" reason is spent.** It read "eight of fourteen clan-owned tables carry no policy", which was 2026-08-13 data. Read on 2026-10-04: all thirteen clan-owned tables carry row-level security and at least one policy (migration 039 dropped `clan_settings`), and the gate fails if one is left out (`backend/tests/integration/test_rls_activation.py:617-643`). M1's open issues that day were in a test gate, a domain rule, and a storage adapter. None changes what a screen sees, except one new error code that the documents slice renders, sixth in M2's order. Decided in #164 | [ADR-008](decisions/008-rls-defense-in-depth.md), [`architecture/multi-tenancy.md`](architecture/multi-tenancy.md), issue #164 |
| Inside **M1**, the two privacy toggles come before any screen that shows them — **discharged 2026-08-22, and the rule it encoded still binds** | A privacy control that restricts nothing is the most dangerous control in the product: the operator believes the tree is private and it is not. This boundary is now satisfied because **there are no toggles**: ADR-044 dropped `allow_public_tree` and `privacy_level` rather than enforce them, and ADR-054 dropped the `clan_settings` table they lived in. **The rule outlives the columns** — if the concept returns, ADR-044 § 2 fixes the four terms it returns on, and enforcement still ships before any screen | [ADR-044](decisions/044-privacy-toggles-dropped-from-v1.md) § 2, [ADR-054](decisions/054-clan-settings-table-is-dropped.md); [design spec](superpowers/specs/2026-08-02-design-system-and-screens.md) § 9-J21 for the rule itself |
| **M2** runs the web slices in the spec's own order | The sequence is already decided and dated: auth, persons, relationships, tree, events, documents, then admin. Each pull request migrates its slice **and** deletes the matching legacy code | [web architecture spec, lines 208-219](superpowers/specs/2026-08-02-web-architecture-observability-design.md) |
| Inside **M2**, auth is first and persons is second | Auth gives every later slice a trustworthy clan context. Persons is the reference slice the other five copy, so no later slice can be planned until it lands | [web architecture spec, lines 211-212](superpowers/specs/2026-08-02-web-architecture-observability-design.md) |
| Inside **M2**, the tree slice is last among the read slices | It is the heaviest: XYFlow plus the tree read-model plus performance on a clan of several thousand people. Scheduled once the pattern is stable | [web architecture spec, line 258](superpowers/specs/2026-08-02-web-architecture-observability-design.md) |
| **M3**, deploy and operate, before real data arrives | **Not verified.** No source read on 2026-08-13 orders the restore drill against the first real clan. The reasoning is the maintainer's: a backup nobody has restored is not a backup | |
| **M4**, mobile M1 through M4, after the web slices | The maintainer's decision of 2026-08-13, from the target above. **Not verified** as a technical constraint: nothing makes mobile depend on the web app | |
| Inside **M4**, no mobile milestone is planned before the M0 device walk | M0's own definition of done is "proven on a device". Planning M1 against an unproven spine inherits its mistakes | The mobile M0 device walk, which nobody can run from a terminal in this repository |

**Three of the nine rows say "not verified", and that is the finding rather than a gap in the work.**
The order is the maintainer's and is real. The reasons behind three of its boundaries are written
down nowhere.

## Where each milestone stands

No status lives here. GitHub Issues owns it. This table says only what each milestone is for, so a
reader knows where to look.

| Milestone | What it is for |
|---|---|
| **M0** Make the surface verifiable | The colour tokens, the fonts, contrast, the primary-colour decision, dark mode, a gate so the class of defect cannot return, and the 200%-text-scale defect |
| **M1** Finish clan isolation and the data rules | Row-level security on every clan-owned table, the two privacy toggles (dropped, not enforced: ADR-044, ADR-054), invitation expiry, field-level visibility as the two-field contact rule (ADR-049), edges hidden on read when either person is soft-deleted (ADR-051, which withdrew the cascade), and the first dated restore drill, run on local data (`ops/backup-restore.md`). All six were met by 2026-08-22, read at source on 2026-10-04 in #164. M1 also holds the isolation and data-rule defects found since |
| **M2** The web slices | Auth, then persons as the reference slice. Relationships, tree, events, documents, and admin follow once persons lands |
| **M3** Deploy and operate | The Pulumi decision, the monitoring set, and the first restore drill against a production dump (`ops/backup-restore.md`, go-live checklist). Each needs a decision or an environment first |
| **M4** Mobile M1 to M4 | Triggered by the M0 device walk |

**Later milestones deliberately carry no open issues.** An issue claims to be actionable today, and
that claim has to be true. Work whose trigger is not met stays off the board.

## The three shapes of blocker, and why they are tracked differently

| Shape | Where it lives | Example |
|---|---|---|
| Work one agent can finish | a GitHub issue labelled `ready-for-agent` | A policy on `change_requests` |
| Work that needs a decision first | a GitHub issue labelled `ready-for-human`, blocking the rest | The decision that repaints the product |
| Work nobody in this repository can do | a GitHub issue held open with its owner and trigger named in the body | The mobile M0 device walk |

**One owner action still blocks shipped code**: the mobile M0 device walk. Three of the original
four are discharged. `delete-branch-on-merge` read `true` on 2026-09-04. Under #163, on 2026-10-04,
the hosted project's buckets were created and verified, and the email-template format was recorded
([ops/supabase-hosted-project.md](ops/supabase-hosted-project.md)). The buckets did not need the
dashboard after all: once the owner had logged the CLI in, `supabase seed buckets --linked` created
them from `supabase/config.toml`.

## Restarting the agent team

Four agent definitions live in [`../.claude/agents/`](../.claude/agents/): `backend-engineer`,
`web-engineer`, `flutter-engineer`, and `product-designer`. Each carries this project's gates, so a
dispatch only needs to say *what*, not *how*.

Four rules apply when more than one runs at a time. Each cost real time to learn.

- **Every parallel backend dispatch sets its own `TEST_PG_DB_NAME`.** The integration harness drops
  its throwaway database `WITH (FORCE)`, so two runs sharing the name drop each other's. It cost 182
  spurious failures in one session. ADR-016 made the name an env var, which makes concurrent runs
  safe **only if each dispatch sets it**.
- **Agents never push and never open pull requests.** They commit to a worktree branch and stop.
  This caught a defect no single agent could see: two backend branches, each green alone, red
  together.
- **Re-run the gate on the combined tree.** Per-branch green proves nothing about the composition.
- **Fence file territory** when two agents touch adjacent surfaces, and rebase the moment `main`
  moves underneath.

**Give each dispatch one issue.** An issue carries its own evidence, its own end state, and its own
verification, so a dispatch is one line plus an issue number.

## What this file is not

- **Not a status board.** GitHub Issues is, in one place.
- **Not a plan.** An issue holds the end state and the verification for one unit of work.
  `superpowers/specs/` holds the designs. `superpowers/plans/` receives nothing new.
- **Not binding.** The order above is reported, with its author named per row. Where a row disagrees
  with the ADR or spec it cites, this file is the bug.
