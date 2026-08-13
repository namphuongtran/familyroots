# Seeds, and how work is planned here

This file carries no `paths` field, so it loads in every session. It holds the standing rule for
how work is planned and how it is explained. [`docs/SEEDS.md`](../../docs/SEEDS.md) is the
tracker itself, and this file is not a summary of its contents.

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
