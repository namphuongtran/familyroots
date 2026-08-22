# Seeds, and how work is planned here

This file carries no `paths` field, so it loads in every session. It holds the standing rule for
how work is planned, how it is explained, and how a test is written so that it can fail.
[`docs/SEEDS.md`](../../docs/SEEDS.md) is the tracker itself, and this file is not a summary of its
contents.

Adopted 2026-08-13, on the maintainer's instruction, after two planning files went stale without
anything catching it. `docs/roadmap.md` and `docs/work-register.md` both read "Last updated:
2026-08-03". By 2026-08-13 the first listed audit `ip_address`/`user_agent` as dormant work when
`backend/app/models/audit_log.py:36-37` already declared both columns and
`backend/app/infrastructure/event_dispatcher.py:87` already wrote them. Nothing was wrong with
the code. What was wrong is that the plan and the tree disagreed, and the plan was the thing an
agent read first.

## The rule, in one paragraph

**Work is planned as seeds.** A seed is one issue, scoped to what a single agent can finish in one
sitting, carrying enough context to be worked without reading the conversation that produced it.
Seeds are **forward chained**: each one names what blocks it and what it unblocks, so a reader can
look at the set and see which seeds are actionable right now without reasoning about the rest.
Never write one large issue where three small ones would do, and never open a pull request that
closes more than one seed unless the seeds are the same change.

## What each of the four words means, because they are doing real work

**Detailed** means a second agent does not have to re-derive what you already read. Name the file
and the line for every claim the seed rests on. If the seed depends on a measurement, put the
number and the date in the seed, not a pointer to a conversation.

**Declarative** means the seed states the **end state** and how to **check** it, not a list of
keystrokes. Write "`clan_settings` carries an RLS policy and a two-sided isolation test proves it"
rather than "add a migration". The reason is that a procedure goes stale the moment the tree moves,
while an end state stays checkable. A seed whose verification cannot be run is not finished being
written.

**Forward chained** means the dependency edges are written down in both directions. `Blocked by`
lets an agent skip a seed it cannot start. `Unblocks` lets the agent who finishes one know what
became available, which is the half that is usually left out and the half that keeps the set moving.
A seed with no `Blocked by` entry is claiming to be actionable today, so that claim has to be true.

**Single-agent-sized** is the hardest one to hold and the easiest to check. The test is: can one
agent reach the seed's end state, run its verification, and commit, without a second decision from
the maintainer? If the honest answer is no, the seed contains a decision, and the decision is its
own seed that blocks the rest.

## The fields a seed carries

| Field | What it holds |
|---|---|
| ID | `S-NNN`, never reused, never renumbered |
| Title | One line, imperative, naming the end state |
| Status | `open`, `blocked`, `in progress`, or `done` |
| Blocked by | Seed IDs, or `none` |
| Unblocks | Seed IDs, or `nothing yet` |
| End state | What is true when the seed is done, in checkable sentences |
| Verification | The commands to run, and what their output must say |
| Sources | Every `file:line` the seed rests on |
| Out of scope | What a reader might reasonably expect and will not get |

The last field earns its place. A seed that does not say what it excludes gets read as covering
more than it does, which is the same defect as an unsourced claim reaching a later reader.

## The `Verification` field names a gate set, and the gate set is not negotiable

The root [`CLAUDE.md`](../../CLAUDE.md) owns the commands. A seed names which set applies and does not
restate the commands, because a copied command line goes stale:

| A seed touching | Names |
|---|---|
| `backend/**` | the backend full quality gate, `CLAUDE.md:76` |
| `web/**` | the full web gate in `web/CLAUDE.md`, which is longer than the two commands at `CLAUDE.md:78` |
| `mobile/**` | the mobile full quality gate, `CLAUDE.md:80` |
| a migration | the backend gate, plus `uv run alembic upgrade head` **and** the matching `downgrade` |
| documentation only | no gate. Say so plainly rather than leaving the field empty |

**A green gate is not evidence about a claim the gate does not check.** Two rules follow, both
learned here:

- **Verify lint with the plain command.** `ruff check .` must print "All checks passed!".
  `ruff check --fix` printing "No fixes available" is **not** success, and reading it as success
  merged red CI three times.
- **Demand a negative control.** Delete the fix, watch the named test fail, put the fix back. A
  test that has never been seen to fail pins nothing. For an isolation seed, plant the inversion
  on purpose: a policy that protects nothing and a policy that works both pass a green suite.
  **A control proves the test can fail. It does not prove the test can fail for the right reason.**
  That is the next section, and it is the one this repository has got wrong three times.

## A test pins an outcome, not a setting

**Adopted 2026-08-22 by seed S-051, after the third instance in three weeks.** Every time, the
defect was found by accident, by an agent doing something else. Every time, it was written down
only in the folder that agent happened to be working in. `.claude/rules/tailwind.md` § 2,
`backend/CLAUDE.md`, and `mobile/CLAUDE.md` note 6 each hold their own instance and its
measurements. This section is the one place the rule itself lives. `.claude/rules/tailwind.md` § 2
and `mobile/CLAUDE.md` note 6 point here, changed by S-051. `backend/CLAUDE.md` was fenced to a
concurrent agent on 2026-08-22, so S-051 handed its pointer text to the coordinator rather than
editing the file. If that file does not carry the pointer, it is still owed.

**The rule.** Assert the **outcome** the code is meant to produce. Never assert the **setting**
the code sets in order to produce it. A setting is a fact the code already guarantees, so an
assertion on it cannot fail for the reason anyone cares about. This extends "Demand a negative
control" above rather than replacing it. The control proves the test can fail. This rule is about
whether it can fail for the **right** reason.

### The three instances, each read at source

**1. `web`, seeds S-001 and S-003, measured 2026-08-13.** The check was a Chromium probe: set
`color: hsl(var(--<name>))` on an element and read `getComputedStyle` back. The design spec
prescribes exactly that at
`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:405-409`. Tailwind v4 emits an
`@theme` variable only when a generated rule references it, so a token that no class in `web/src`
uses is **absent** from the built CSS, and the declaration falls back to the inherited body
colour. Re-measured on `/vi/login`, in `next dev` on `:3210` and in a production build: only
`border` and `foreground` returned their declared hex, and the other fifteen returned
`lab(8.11897 0.811279 -12.254)`. **That is the same value S-001 had recorded as its negative
control**, so a pass and a failure were one reading. S-003 withdrew S-001's whole table of
seventeen computed values. The fix that S-001 landed still holds. The measurement does not.

**One difference is worth stating.** This instance was a probe run by hand and recorded as a
seed's evidence, not a test in the suite. The shape is the same and the cost was the same: a later
reader took a table of seventeen values as fact. It is also the loosest fit to this rule's own
wording. The probe was reaching for an outcome, but the outcome it read did not depend on the token
at all. Question 2 below is the form that catches this one.

**2. `backend`, seeds S-012 and S-014, measured 2026-08-22.** The coverage guard
`test_rls_coverage_enabled_tables_have_policy_and_grants` asserted `n_policies >= 1` for every
RLS-enabled table, plus the role grants. Read at
`backend/tests/integration/test_rls_activation.py:167-211`, at commit `2623b47`, the parent of
S-012's `d0edaf0`. In one sentence it asserted "RLS is on and the table has at least one policy".
A policy flipped to `USING (true) WITH CHECK (true)`, which hands the request role every clan's
rows, **passes it**. S-012 split the guard into `_CLAN_ISOLATED_TABLES` and
`_REQUEST_ROLE_DENIED_TABLES`, and asserted each half with its own question.

**The split then failed the same way one level up, and that is the sharper half.** S-014 found
`audit_logs` fits neither set, because its reads are clan-keyed and its INSERT admits any clan or
none. With `audit_logs_sel` flipped to `USING (true)`,
`test_each_half_of_the_rls_set_matches_what_its_policies_do` stayed **green**. S-014 added a third
set rather than moving the name into a set that passed.

**3. `mobile`, seed S-049, measured 2026-08-22.** The assertion was
`expect(theme.dividerTheme.thickness, 0)`, under the name "the no-line rule: dividers have no
thickness". Read at `mobile/test/core/theme/theme_test.dart:129,131`, at commit `27a446f`.
Thickness zero is not absence. Flutter says so in its own doc comment, read at source 2026-08-22
in `/Users/southern/development/flutter/packages/flutter/lib/src/material/divider.dart:86-87`: "A
divider with a [thickness] of 0.0 is always drawn as a line with a height of exactly one device
pixel." The assertion was true and green from `0785036` on 2026-08-03 to `527a745` on 2026-08-22,
while the theme went on choosing the colour of the line it claimed to suppress.

**What was not true, and S-051 corrected it here.** Its own summary said the app painted a line for
19 days. It did not. No file under `mobile/lib` used `Divider` or `VerticalDivider` in that window.
S-049 checked it on 2026-08-22, and S-051 re-checked it the same day: `grep -rn "Divider"
mobile/lib` returns 14 lines, and every one of them is a localisation key named `orDivider`, a
comment, or the `dividerTheme` declaration itself. No widget uses one. The real defect is that the
first screen to add a divider would have drawn the forbidden line with the suite still green. That
is bad enough. Do not overstate it.

### What to assert instead

Render and read pixels. Execute and read the statement. Request and read the response.

| The subject | Not this | This |
|---|---|---|
| a rule about paint | a theme field holds a value | rasterise a real widget and read every pixel back. `mobile/test/core/theme/theme_test.dart`, "the no-line rule: a real Divider paints no pixel", puts a `Divider` in a `RepaintBoundary`, calls `toImageSync`, and asserts the set of distinct pixels is exactly `{ground}` |
| a database policy | the catalog says a policy exists | run the statement as the request role under clan A and clan B, and read which rows come back, per command. `backend/tests/integration/test_rls_activation.py` |
| a style token | a computed style read back through `var()` | compile the token with a class that references it, and require the substituted value to parse as a colour. `web/src/app/theme-tokens.test.ts`. `web/src/app/contrast.test.ts` reads `globals.css`, which holds the value unconditionally |
| an API shape | the handler ran | send the request and read the response body |

### Two questions that catch it

1. **Name the failure the test exists to catch, then plant that failure.** If the test stays
   green, it pins nothing. The `backend` guard and the `mobile` assertion both stayed green under
   the exact defect each was named for.
2. **Check that the failing reading differs from the passing reading.** S-001's probe fails this
   question: its pass value and its negative-control value were both
   `lab(8.11897 0.811279 -12.254)`. A control that reads the same either way is not a control.

**A set is a setting too.** S-014's finding is the general form. A guard that asks "is this name in
the covered list" pins the list, not the coverage. When a subject fits none of the sets a guard
carries, add a set. Do not move the name into a set that passes.

### Why this is a rule here and not ADR-049

S-051 pre-allocated ADR number 049 and left the choice to the agent closing it. **No ADR was
written by S-051, and it released the number.** Seed **S-053** took 049 the same day, on
2026-08-22, for field-level visibility, so
[`ADR-049`](../../docs/decisions/049-contact-pii-is-the-whole-field-visibility-rule.md) exists and
is not this rule. A released number is free, not reserved. Three reasons S-051 wrote no ADR,
recorded so nobody re-opens the question:

- **Every ADR in this repository decides something about the system it builds**, and this decides
  how the repository verifies. Counted 2026-08-22 by reading all 46 rows of
  `docs/decisions/README.md`, numbers 001 to 048 with 044 and 046 allocated but unwritten: every
  title names a schema, a policy, a contract, a palette, or a runtime behaviour. None is about how
  an agent works. `.claude/rules/` is the surface that owns that, and this file was adopted the
  same way on 2026-08-13: a dated paragraph in its own header, and no ADR.
- **An ADR does not load into a session.** S-051's end state is a rule written once where every
  session reads it. An ADR would either miss that, or force the rule into two places, which is the
  defect S-051 was opened to fix.
- **`docs/decisions/README.md` is the index every ADR is listed in, and it was fenced to another
  agent on 2026-08-22.** An ADR written here would have landed unindexed. The Maintenance section
  of `docs/SEEDS.md` already records that the index has been wrong about which numbers are taken.

**Why this file, and the one thing that is not established.** This section is here rather than in
a new rule file because this file is **observed** to load. Measured 2026-08-22: the session that
wrote this rule received the root `CLAUDE.md` and this file as project instructions, and did not
receive `.claude/rules/nextjs.md` or `.claude/rules/tailwind.md`, which both carry a `paths:` field
scoped to `web/**`. That is one observation from one session. **Whether a `paths:` glob loads its
file when a matching file is edited has still not been tested here**, and `docs/SEEDS.md` carries
that row in its `Not verified` register. A new rule file with no `paths:` field would probably load
the way this one does. "Probably" is why the rule went here instead.

## Explain the idea in prose before and while you work

Alongside the seed, write the reasoning in plain prose, aimed at the next agent rather than at a
reviewer who already agrees with you. This is not a summary of the diff, which git already holds.
It is the part that does not survive in code: why this shape rather than the obvious one, which
sources disagreed and how that resolved, and what you looked at and decided not to do.

Where that prose lives depends on what it is about, and the choice is not free:

- A decision goes in an ADR under `docs/decisions/`.
- A change to a request or response shape goes in the matching `docs/contracts/rest-*.md`, in the
  same pull request. That is already the root `CLAUDE.md` rule; the seed does not relax it.
- A trap learned by getting something wrong in a folder goes in that folder's `CLAUDE.md`, or in
  the matching `.claude/rules/` file when one owns the surface.
- Everything else goes in the seed and in the commit message.

Do not put the prose only in a chat reply. A chat reply is the one place no future agent reads.

**Pre-allocate the ADR number in the seed.** Every agent left to pick the next free number picks
the same one. The highest number on `main` was 040 on 2026-08-13, so a seed needing an ADR names
041, 042, and so on in its own text, and the seeds that need them do not overlap.

## Where seeds live, and the two other kinds of record beside them

**One tracker holds all three kinds:** [`docs/SEEDS.md`](../../docs/SEEDS.md). The boundary is
between kinds of record inside that file, rather than between files.

| Kind | Holds | Carries an end state |
|---|---|---|
| a seed | one unit of work, actionable or blocked by a named seed | yes, and a verification |
| an `Owed` row | an item owed, with an owner and a trigger that is **not met** | no, because it is not actionable |
| a `Not verified` row | a claim this repository has not established | no, and it may not be cited as fact |

**A register row becomes a seed when its trigger is met, and the row is deleted in the same
change.** It never lives in both places, because a second place recording completion is a second
place to be wrong. That is the failure this rule was adopted to stop.

**Write a register row, not a seed, when the trigger is not met.** A seed with no `Blocked by`
entry claims to be actionable today, and that claim has to be true. The four owner actions on
2026-08-13 are the clearest case: nobody working in this repository can create a Supabase bucket,
so none of them is a seed.

[`docs/roadmap.md`](../../docs/roadmap.md) holds no work of any kind. It holds the milestone order
and the reason for each boundary. Where a boundary rests on nobody's source, it says so.

## Where the generic answer is wrong here

| A generic answer reaches for | This repository decided |
|---|---|
| One issue per feature | One seed per single-agent unit of work, and a feature is usually several |
| A checklist of steps | An end state plus a verification, because a procedure goes stale and a state does not |
| "Blocked by" only | Both directions, so finishing a seed tells you what opened up |
| Putting the plan in the pull request description | The seed is the durable artifact; the pull request closes it |
| One pull request per plan | **One pull request per seed.** 21 task-plans shipped here before this rule, several as multi-task pull requests: #147 carried Tasks 6 to 10 at once. Nobody could pick one of those up halfway |
| A status column in the roadmap | The board in `SEEDS.md` owns status. `roadmap.md` holds order and reasons |
| Tracking state in a second file | One tracker. `docs/work-register.md` was deleted on 2026-08-13 for exactly this reason |
| Explaining the change in the chat reply | Prose goes in the ADR, the contract, the folder `CLAUDE.md`, the seed, or the commit message |

## What the existing planning layer is still for

`docs/superpowers/specs/` stays. A spec is a design, it owns its subject, and a seed cites it.
Where a seed and a spec disagree, read the spec at source before deciding which is the bug.

`docs/superpowers/plans/` receives nothing new. The 21 plans there stay as the record of what was
built, and several of them are the best account of a trap that exists. New work is decomposed into
seeds instead.

## Running more than one agent at a time

These four cost real time to learn. They are rules, not advice.

- **Every parallel backend dispatch sets its own `TEST_PG_DB_NAME`.** The integration harness
  drops its throwaway database `WITH (FORCE)`, so two runs sharing the name drop each other's. It
  cost 182 spurious failures in one session. ADR-016 made the name an env var, which makes
  concurrent runs safe **only if each dispatch sets it**.
- **Agents never push and never open pull requests.** They commit to a worktree branch and stop.
  This caught a defect no single agent could see: two backend branches, each green alone, red
  together.
- **Re-run the gate on the combined tree.** Per-branch green proves nothing about the composition.
- **Fence file territory** when two agents touch adjacent surfaces, and rebase the moment `main`
  moves underneath.
