# ADR-060: A Web Slice Deletes Its Own Legacy and Re-Points Every Importer, and the Legacy Can Only Shrink

## Status

Accepted (2026-10-04). Resolves issue #161, "How does a slice delete its legacy when a later slice
still imports it?", on the map in issue #158. The maintainer chose every option below in a grilling
session on 2026-10-04.

**This ADR ships no runtime code.** The diff is this file, its index row, the web architecture
spec's § 3.2 and § 5.1, and `web/CLAUDE.md` "Migration notes". Documentation only, so no gate
applies. The code is in two build issues: #171 builds the gate in § 4, and #172 deletes the persons
slice's legacy under § 2.

Every reading below was taken on **2026-10-04** at commit `3b9bb3e` on `main`. Treat its line
numbers as hints and its quoted text as the claim.

## Context

### The rule that could not be obeyed

The web architecture spec, `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`,
§ 5.1, said: "Each PR migrates its slice **and** deletes the corresponding legacy code. No PR only
adds." Its § 3.2 lists the legacy trees: `src/lib/api/`, `src/lib/hooks/`, `src/application/`,
`src/infrastructure/`, `src/types/`, `src/lib/types/`, `src/components/<feature>/`, and `axios`.

The persons slice, the spec's reference slice, could not meet it. Its legacy is still imported by
slices the spec orders after it:

| Importer | Slice | What it imports | Replacement in `features/persons/index.ts` |
|---|---|---|---|
| `src/components/family-tree/MemberSidebar.tsx:9` | tree | `usePerson` from `@/lib/hooks/useMembers` | `usePerson`, but it returns the domain `Person`, not the snake_case legacy shape. The sidebar reads about fifteen fields |
| `src/components/family-tree/MemberNode.tsx:6`, `MemberSidebar.tsx:6` | tree | `MemberAvatar` from `@/components/members/` | `PersonAvatar` |
| `src/components/admin/PendingUsersList.tsx:5` | admin | `MemberAvatar`, used at `:60` for a pending **account**, `fullName={user.label} gender="unknown"` | none, and none is wanted. An account is not a person |
| `src/lib/hooks/useRelationships.ts:22` | relationships | `personKeys`, only to invalidate `…'marriages'` (`:29`) and `…'parent-child'` (`:58`) | nothing needed. No query in `src` reads either key, so both invalidations do nothing |

Measured with
`grep -rnE "from ['\"]@/(lib/hooks/useMembers|application/persons|infrastructure/persons|lib/api/members|components/members)" web/src`
and `grep -rnE "personKeys|'marriages'|'parent-child'" web/src`.

### What the repository was already doing

It practised a fourth rule nobody had chosen. The header of `src/lib/hooks/useMembers.ts` says "a
shared legacy file survives, trimmed to what a *different* slice still needs, until that slice's own
deletion seed lands", and `web/CLAUDE.md` "Migration notes" records `axios.ts` as the precedent.
That rule has no end condition. It is how three replaceable imports and two dead invalidations
stayed in place.

### "Frozen, not extended" was prose

`web/CLAUDE.md` "Migration notes" says the legacy trees "are frozen, not extended". Nothing checks
it. `web/.dependency-cruiser.cjs` puts the legacy trees in `options.exclude`, so they are not in the
graph at all, and no rule can see an edge into them. A new `import … from '@/lib/hooks/useAuth'` in
a migrated slice passes CI.

### Persons is not legacy-free from the other side either

Persons' own routes import legacy code that belongs to auth:
`src/app/[locale]/(dashboard)/members/new/page.tsx:8` and `members/[id]/edit/page.tsx:13` both
import `useCapabilities` from `@/lib/hooks/useCapabilities`. The spec's § 5.1 puts capabilities in
the auth slice, PR 1.

## Decision

### 1. Legacy code falls into three kinds, and a slice answers for one of them

| Kind | What it is | Today's examples | Who deletes it |
|---|---|---|---|
| **Slice-owned** | Legacy code that models this slice's own concept | `application/persons/`, `infrastructure/persons/`, `lib/api/members.ts`, `lib/hooks/useMembers.ts` including `personKeys`, the `Person` type in `lib/types/member.ts` | The slice, in its own pull request |
| **Cross-cutting** | Legacy code no single slice owns | `lib/api/axios.ts`, `infrastructure/http/request-context.ts`, `lib/types/index.ts` | The last slice that imports it, as `web/CLAUDE.md` already says of `axios.ts` |
| **Misfiled primitive** | Generic code filed in a slice's folder that is not about that slice | `components/members/MemberAvatar.tsx`, which only draws initials and serves accounts as well as persons | The slice that finds it moves it to `shared/ui`, rather than deleting it or re-pointing it at the slice's own component |

### 2. A slice re-points every importer of its slice-owned legacy, then deletes it

In the same pull request that migrates it, a slice re-points each import of its slice-owned legacy,
wherever that import sits, at the slice's own `index.ts`. Then it deletes the legacy. Adapting an
importer in another slice to the new domain shape is part of the cost of migrating, not scope creep.
For persons, that means adapting `MemberSidebar` from the legacy `Member` to `Person`.

**The fallback is narrow.** A slice-owned legacy file may stay, trimmed, only where the slice's
`index.ts` has no replacement for what the importer uses. When that happens, the build issue of the
**importing** slice owns the file, and its End state names it. There is no deadline: issue #159
decided this repository keeps no staleness clock. Today's one case is `PersonSummary` in
`lib/types/member.ts`, which `lib/types/tree.ts:3` embeds in tree's response type. Persons has no
equivalent for tree's wire shape, so the file is trimmed to `PersonSummary` and the tree slice
deletes it.

### 3. A slice is done when both halves hold

1. **None of its slice-owned legacy remains**, except under § 2's fallback.
2. **It imports no legacy code.**

The spec's order already implies the second half for persons, because auth comes first. Under § 2,
the auth slice re-points persons' two `useCapabilities` imports when it migrates capabilities, so
persons needs no issue of its own for that half.

### 4. "Frozen, not extended" becomes a gate that only shrinks

A dependency-cruiser rule forbids any module outside the legacy trees from importing a legacy path.
Today's violations sit in a committed baseline (`depcruise --ignore-known`), and CI fails if a pull
request **adds** an entry to that baseline. Removing entries is how the migration shows progress.
This is the web counterpart of ADR-013's `ignore_imports` ratchet.

The baseline is a list, and `.claude/rules/testing.md` says "A set is a setting too". So the gate
proves itself on the outcome: a planted new legacy import must fail CI, **and** the same import with
the baseline regenerated to admit it must also fail.

## Consequences

Easier:

- "Is this slice done?" has a checkable answer: two greps and a baseline diff.
- The spec's slice order stands. Nothing has to move ahead of persons.
- Legacy can only shrink, by construction, rather than by reviewer memory.

Harder:

- A slice's pull request edits files in slices that have not migrated yet. The persons deletion
  rewrites part of tree's `MemberSidebar` for that reason. Tree's own pull request then starts from
  a sidebar that already reads `Person`.
- The baseline is one more file to keep, and a pull request that deletes legacy has to shrink it in
  the same change.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep the rule, and call a slice done only after its importers migrate | Reverses the spec's order: tree and admin would come before persons closes. Tree is meant to copy a stable persons pattern, so each would wait on the other |
| "Delete what only this slice used", with a named owner and a deadline for shared leftovers | This was already the de facto practice, and it is how the leftovers in § Context stayed. The deadline needs a clock, and issue #159 decided against one |
| Replace the rule with a gate alone | A gate stops growth, but it does not say when a slice is done |

## What this ADR deliberately does not decide

- **Which slice owns each cross-cutting file's final deletion.** `web/CLAUDE.md` already says "the
  last slice". This ADR does not name it ahead of time.
- **Whether the persons slice is otherwise a finished reference pattern**: its tests, its screens,
  its `HistoricalDate` rendering. This ADR defines done for legacy only.
- **The tree sidebar's links.** `MemberSidebar.tsx:83` and `:90` link to `/persons/{id}` and
  `/persons/{id}/edit`, and no `persons` route exists under `src/app/[locale]`. The persons routes
  live under `members/`. That defect belongs to the tree slice.

## Related

- [ADR-013: Machine-Enforced Boundaries (import-linter + Ratchet)](013-import-linter-boundary-ratchet.md):
  the backend ratchet § 4 mirrors.
- [Web architecture spec](../superpowers/specs/2026-08-02-web-architecture-observability-design.md):
  § 3.1 defines the layer rules dependency-cruiser enforces, and § 3.2 and § 5.1 now point here.
