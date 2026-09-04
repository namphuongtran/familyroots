# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## What a `ready-for-agent` issue carries

Decided 2026-09-04, resolving issue #159 on the map in issue #158. It replaces the nine-field seed
format that `.claude/rules/seeds.md` held until commit `ec73452` deleted it. Recover that file with
`git show ec73452^:.claude/rules/seeds.md`.

### GitHub carries the state, the body carries the claim

Four of the seed format's nine fields were state, and state now lives in GitHub alone. Do not write
any of them into the body. A field written in two places is a field that can disagree with itself,
and that is what went wrong: seed `S-093` said `Status: open` in its own body while the status board
in the same file said `done`.

| The old seed field | Where it lives now |
|---|---|
| ID | the issue number |
| Status | the issue state, open or closed |
| Blocked by | GitHub issue dependencies, per "Blocking" below |
| Unblocks | the same dependency read from the other end. GitHub renders both directions, so write the edge once |
| Sources, End state, Verification, Out of scope | the body, per the next section |
| area, which the seed format had no field for | an `area:*` label, because the label picks the gate set |
| milestone, which the seed format had no field for | a GitHub milestone, M0 to M4, matching `docs/roadmap.md` |

`docs/roadmap.md:63` says later milestones deliberately carry no open issues. The milestone field is
what makes that rule checkable.

**Provenance is native too.** GitHub records the author and the creation date, and it links any issue
whose number you mention. So do not restate who filed the issue or when. Name the issue it came from
by number and let GitHub draw the edge.

### The four sections, all of them mandatory

Optional prose may come first, to say why the work matters and why it is actionable now. Then these
four, in this order. None may be empty.

1. **End state.** What is true when the issue is done, in sentences a reader can check. State the end
   state, never a list of keystrokes. A procedure goes stale the moment the tree moves. An end state
   stays checkable.
2. **Verification.** Name the gate set that the root `CLAUDE.md` owns, and do not restate its
   commands, because a copied command line goes stale. `.claude/rules/testing.md` maps the surface to
   the set. Then name the specific reading that proves this change, and its negative control. For work
   that touches documentation only, write "no gate" in words rather than leaving the section thin.
3. **Sources.** Every `path:line` the issue rests on, each with the short commit SHA it was read at.
   Quote the text of any claim the issue turns on. See "How a claim is cited" below.
4. **Out of scope.** What a reader might reasonably expect and will not get. Where there is nothing,
   write that there is nothing. An issue that excludes nothing gets read as covering more than it does.

`.github/ISSUE_TEMPLATE/ready-for-agent.md` carries these four sections, so
`gh issue create --template ready-for-agent.md` seeds them. This file holds the reasons. The template
holds the shape.

### One agent, one issue, no second decision

Before applying `ready-for-agent`, answer this question: can one agent reach the end state, run the
verification, and commit, without a second decision from the maintainer? If the answer is no, the
issue contains a decision. File the decision as its own issue, and make it block this one.

The filer applies the label. There is no separate review step, because a review step nobody performs
fails the same way a clock nobody reads fails.

### How a claim is cited

- **A source reading** carries `path:line` and the short commit SHA it was read at. Quote the text
  when the claim turns on it. Seed `S-087` still reproduces today, without the tracker that held it,
  because it quoted the two patterns that disagree rather than only their line numbers.
- **A measurement** carries the command, its output, and the date it was run. A count with no command
  cannot be re-taken.

### Nothing keeps a filed issue fresh, and that is the decision

There is no staleness clock, no scheduled re-check, and no CI job that validates citations. This is
deliberate, not an omission.

An old number was never the failure. The failure was a reader trusting an old number.
`docs/roadmap.md` was rewritten on 2026-08-13 because two status files went stale, and on 2026-09-04
it still carried four claims that measured false. A clock would have labelled those claims old. It
would not have made anyone re-read them.

**So the freshness rule sits at the point of use.** An agent taking a `ready-for-agent` issue re-runs
that issue's own cited commands first. It posts the readings as its opening comment, with the date.
Three outcomes follow:

- The readings agree with the issue. Say so, then proceed.
- The readings disagree. Comment with the new readings, remove `ready-for-agent`, add `needs-triage`,
  and stop.
- The defect is already fixed. Close the issue, quoting the reading that shows it.

A citation check in CI would pass on a file that still exists but no longer holds the claim. The
evidence rule names that as the dangerous citation: the pointer resolves, so every mechanical check
is green, and the claim is still not there.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
