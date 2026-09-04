# How a test is written here, so that it can fail

This file carries no `paths` field, so it loads in every session. It holds the standing rule for
verification: which gate applies to which surface, and what a test is allowed to assert.

## The gate set is not negotiable

The root [`CLAUDE.md`](../../CLAUDE.md) owns the commands. Name which set applies and do not restate
the commands, because a copied command line goes stale:

| Work touching | Runs |
|---|---|
| `backend/**` | the backend full quality gate, `CLAUDE.md:76` |
| `web/**` | the full web gate in `web/CLAUDE.md`, which is longer than the two commands at `CLAUDE.md:78` |
| `mobile/**` | the mobile full quality gate, `CLAUDE.md:80` |
| a migration | the backend gate, plus `uv run alembic upgrade head` **and** the matching `downgrade` |
| documentation only | no gate. Say so plainly rather than leaving the question open |

**A green gate is not evidence about a claim the gate does not check.** Two rules follow, both
learned here:

- **Verify lint with the plain command.** `ruff check .` must print "All checks passed!".
  `ruff check --fix` printing "No fixes available" is **not** success, and reading it as success
  merged red CI three times.
- **Demand a negative control.** Delete the fix, watch the named test fail, put the fix back. A
  test that has never been seen to fail pins nothing. For an isolation change, plant the inversion
  on purpose: a policy that protects nothing and a policy that works both pass a green suite.
  **A control proves the test can fail. It does not prove the test can fail for the right reason.**
  That is the next section, and it is the one this repository has got wrong three times.

## A test pins an outcome, not a setting

**Adopted 2026-08-22, after the third instance in three weeks.** Every time, the defect was found by
accident, by an agent doing something else. Every time, it was written down only in the folder that
agent happened to be working in. `.claude/rules/tailwind.md` § 2, `backend/CLAUDE.md`, and
`mobile/CLAUDE.md` note 6 each hold their own instance and its measurements. This section is the one
place the rule itself lives.

**The rule.** Assert the **outcome** the code is meant to produce. Never assert the **setting** the
code sets in order to produce it. A setting is a fact the code already guarantees, so an assertion
on it cannot fail for the reason anyone cares about. This extends "Demand a negative control" above
rather than replacing it. The control proves the test can fail. This rule is about whether it can
fail for the **right** reason.

### The three instances, each read at source

**1. `web`, measured 2026-08-13.** The check was a Chromium probe: set `color: hsl(var(--<name>))`
on an element and read `getComputedStyle` back. The design spec prescribes exactly that at
`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:405-409`. Tailwind v4 emits an
`@theme` variable only when a generated rule references it, so a token that no class in `web/src`
uses is **absent** from the built CSS, and the declaration falls back to the inherited body colour.
Re-measured on `/vi/login`, in `next dev` on `:3210` and in a production build: only `border` and
`foreground` returned their declared hex, and the other fifteen returned
`lab(8.11897 0.811279 -12.254)`. **That is the same value the original record had kept as its
negative control**, so a pass and a failure were one reading. The whole table of seventeen computed
values was withdrawn. The fix it recorded still holds. The measurement does not.

**One difference is worth stating.** This instance was a probe run by hand and recorded as evidence,
not a test in the suite. The shape is the same and the cost was the same: a later reader took a
table of seventeen values as fact. It is also the loosest fit to this rule's own wording. The probe
was reaching for an outcome, but the outcome it read did not depend on the token at all. Question 2
below is the form that catches this one.

**2. `backend`, measured 2026-08-22.** The coverage guard
`test_rls_coverage_enabled_tables_have_policy_and_grants` asserted `n_policies >= 1` for every
RLS-enabled table, plus the role grants. Read at
`backend/tests/integration/test_rls_activation.py:167-211`, at commit `2623b47`. In one sentence it
asserted "RLS is on and the table has at least one policy". A policy flipped to
`USING (true) WITH CHECK (true)`, which hands the request role every clan's rows, **passes it**. The
guard was split into `_CLAN_ISOLATED_TABLES` and `_REQUEST_ROLE_DENIED_TABLES`, each half asserted
with its own question.

**The split then failed the same way one level up, and that is the sharper half.** `audit_logs` fits
neither set, because its reads are clan-keyed and its INSERT admits any clan or none. With
`audit_logs_sel` flipped to `USING (true)`,
`test_each_half_of_the_rls_set_matches_what_its_policies_do` stayed **green**. A third set was added
rather than moving the name into a set that passed.

**3. `mobile`, measured 2026-08-22.** The assertion was `expect(theme.dividerTheme.thickness, 0)`,
under the name "the no-line rule: dividers have no thickness". Read at
`mobile/test/core/theme/theme_test.dart:129,131`, at commit `27a446f`. Thickness zero is not
absence. Flutter says so in its own doc comment, read at source 2026-08-22 in
`packages/flutter/lib/src/material/divider.dart:86-87`: "A divider with a [thickness] of 0.0 is
always drawn as a line with a height of exactly one device pixel." The assertion was true and green
from `0785036` on 2026-08-03 to `527a745` on 2026-08-22, while the theme went on choosing the colour
of the line it claimed to suppress.

**What is not true, and it matters.** The app did **not** paint a line for 19 days. No file under
`mobile/lib` used `Divider` or `VerticalDivider` in that window. Checked twice on 2026-08-22:
`grep -rn "Divider" mobile/lib` returns 14 lines, and every one of them is a localisation key named
`orDivider`, a comment, or the `dividerTheme` declaration itself. No widget uses one. The real defect
is that the first screen to add a divider would have drawn the forbidden line with the suite still
green. That is bad enough. Do not overstate it.

### What to assert instead

Render and read pixels. Execute and read the statement. Request and read the response.

| The subject | Not this | This |
|---|---|---|
| a rule about paint | a theme field holds a value | rasterise a real widget and read every pixel back. `mobile/test/core/theme/theme_test.dart`, "the no-line rule: a real Divider paints no pixel", puts a `Divider` in a `RepaintBoundary`, calls `toImageSync`, and asserts the set of distinct pixels is exactly `{ground}` |
| a database policy | the catalog says a policy exists | run the statement as the request role under clan A and clan B, and read which rows come back, per command. `backend/tests/integration/test_rls_activation.py` |
| a style token | a computed style read back through `var()` | compile the token with a class that references it, and require the substituted value to parse as a colour. `web/src/app/theme-tokens.test.ts`. `web/src/app/contrast.test.ts` reads `globals.css`, which holds the value unconditionally |
| an API shape | the handler ran | send the request and read the response body |

### Two questions that catch it

1. **Name the failure the test exists to catch, then plant that failure.** If the test stays green,
   it pins nothing. The `backend` guard and the `mobile` assertion both stayed green under the exact
   defect each was named for.
2. **Check that the failing reading differs from the passing reading.** The `web` probe fails this
   question: its pass value and its negative-control value were both
   `lab(8.11897 0.811279 -12.254)`. A control that reads the same either way is not a control.

**A set is a setting too.** The `audit_logs` finding is the general form. A guard that asks "is this
name in the covered list" pins the list, not the coverage. When a subject fits none of the sets a
guard carries, add a set. Do not move the name into a set that passes.

## Where to write down what you learned

- A decision goes in an ADR under `docs/decisions/`.
- A change to a request or response shape goes in the matching `docs/contracts/rest-*.md`, in the
  same pull request. That is already the root `CLAUDE.md` rule.
- A trap learned by getting something wrong in a folder goes in that folder's `CLAUDE.md`, or in the
  matching `.claude/rules/` file when one owns the surface.
- Everything else goes in the GitHub issue and in the commit message.

Do not put the prose only in a chat reply. A chat reply is the one place no future agent reads.
