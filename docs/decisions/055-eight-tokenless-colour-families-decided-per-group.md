# ADR-055: The Eight Tokenless Colour Families Are Decided Per Group, Not Swept

## Status

Accepted and shipped (2026-08-22), after the palette sweep the same day.

## Context

The palette sweep moved 393 hardcoded palette utilities onto the semantic tokens `.claude/rules/tailwind.md`
already gated, and stopped at 41 occurrences across 10 files (plus three raw hex literals in a
non-Tailwind use) that it refused to invent values for. Its own out-of-scope line named "any new
token: if a use has no token, that is a finding for a new seed, not a value to invent here." This
ADR is that seed.

**The 41-plus-3 figure was re-measured on 2026-08-22, before writing anything, per the seed's own
instruction that the count moves with every merge.** Every file:line the seed cited was re-grepped
at source and matched exactly: `MemberNode.tsx:25,27`, `MemberAvatar.tsx:22-23`,
`RoleSelector.tsx:22`, `PendingUsersList.tsx:72`, `EventCard.tsx:16-17`,
`platform/layout.tsx:16`, `platform/metrics/page.tsx:11-19`, `platform/clans/page.tsx:30`,
`(dashboard)/dashboard/page.tsx:9-21`, `backoffice/dashboard/page.tsx:85,138`, and the three
`TreeCanvas.tsx` hexes at `:67,69,70`. Nothing in the seed's citations was stale.

**Each group asks a different question, which is why this is one ADR with a decision per group
rather than a second sweep.** A token invented to cover a use nobody defended is how a palette
rots — the seed's own words, and the standard this ADR tries to meet for each of the six
decisions below.

## Decision

### 1. Gender coding loses its colour entirely — `MemberNode.tsx`, `MemberAvatar.tsx`, `TreeCanvas.tsx`

**`MemberNode.tsx`'s border** (`border-blue-400` male / `border-pink-400` female / `border-border`
other) and **`MemberAvatar.tsx`'s fill** (`bg-blue-100 text-blue-700` male / `bg-rose-100
text-rose-700` female / `bg-muted text-muted-foreground` unknown) both used colour as the **only**
signal of a member's gender. `grep -rn gender web/src/components web/src/app --include="*.tsx"`
turns up no icon, no label, and no other rendering of gender anywhere these two components sit —
so this was a live spec § 5 `T-06` violation ("colour is never the only channel") **independent of
dark mode**, not merely a token gap.

Adding a second channel (an icon) is new UI scope this decision seed does not take on. The
narrower, immediately correct fix: stop encoding gender in colour on these two surfaces. Both now
take the single neutral treatment the `'unknown'`/other case already used —
`border-border` on the node, `bg-muted text-muted-foreground` on the avatar. `gender` stays a prop
on `MemberAvatar` (every caller already passes it, and a future icon-based indicator would still
need it); it now reaches the DOM only as a `data-gender` attribute, so the prop is not simply dead.

**`TreeCanvas.tsx`'s `MiniMap` `nodeColor`** carried the identical branch as three raw hexes
(`#93c5fd` / `#f9a8d4` / `#d1d5db`), which the seed correctly flagged as the same defect in a form
The sweep's class-grep scope could not see: `@xyflow/react`'s `nodeColor` takes a plain string, not a
CSS custom property, so it cannot read a token and cannot flip with the colour scheme regardless.
Consistent with dropping gender-as-colour above, `nodeColor` is now the single constant
`'#d1d5db'` for every node. **This does not make the minimap dark-mode-correct** — its own
background and `maskColor` (`rgba(0,0,0,.04)`) still do not follow the app's palette at all, a
real and separate gap this decision does not close, because `@xyflow/react` has no token bridge in
this codebase today.

### 2. Role and status: reuse before invent — `RoleSelector.tsx`, `PendingUsersList.tsx`

**`RoleSelector.tsx`'s `editor` state** (`bg-blue-50 text-blue-700 border-blue-300`) is not a
`T-06` violation on its own: each role button already carries its own translated label, so colour
here is reinforcing an already-legible state, not carrying it alone. The question is only whether
a fourth colour family is warranted for one selector state between the existing neutral `viewer`
(`bg-muted`) and elevated `admin` (`destructive`). It is not: `editor` now takes the already
decided, already AA-gated `primary-container` pair — the ordinary leaf-green "this is the normal
collaborating role" — rather than inventing an `info` family spec § 2.1 happens to publish but
that no second surface in this codebase would use.

**`PendingUsersList.tsx`'s approve button** (`border-green-200 bg-green-50 text-green-700`) sits
directly beside an already-tokened reject button (`border-destructive/30 bg-destructive/10
text-destructive`). Approve/reject is a genuine, spec-quoted status pair (§ 2.1's `success` /
`danger` rows), so this is the one group in this ADR that earns a new token: **`--color-success`**,
`#2e6a4e` light / `#8fcfaa` dark, quoted directly from spec § 2.1 and § 2.2's status lines. Only
the bare token is added — no `success-container` or `success-foreground` — because every use below
is `text-success` or `bg-success/10`, mirroring the exact shape `destructive` already uses in this
file. A container pair is added the day a use needs a solid fill, not pre-emptively.

The approve button becomes `border-success/30 bg-success/10 text-success hover:bg-success/15`,
mirroring the reject button's own class shape exactly.

### 3. Event kinds: decoration, not information — `EventCard.tsx`

`birthday` (`bg-blue-50 border-blue-200`) and `wedding_anniversary` (`bg-pink-50
border-pink-200`) are the two remaining untokened entries beside `death_anniversary`
(already `heritage-container`/`heritage`) and `clan_ceremony` (already `accent`/`accent-foreground`
via the sweep's precedent). Spec § 7.8's own card layout example shows every event kind carrying an
explicit type chip and title text (`Giỗ cụ Nguyễn Hữu Đàm [Hằng năm] [Giỗ]`), so the card's
background colour is decoration on top of an already-legible kind, not the identifying channel —
the same question the stat-card group below asks, and the same answer. Both fold into the
existing neutral `custom` treatment, `bg-muted border-border`, rather than gaining two more
one-off families for a distinction the text already makes.

### 4. Platform chrome: reuse the existing notice pair — `platform/layout.tsx`

The super-admin banner (`border-purple-100 bg-purple-50 text-purple-700`) is a standing notice
about an elevated, cross-clan surface. `EventCard.tsx`'s `clan_ceremony` already established
`bg-accent border-accent-foreground/30` as this codebase's "special/notice" treatment; the banner
now reuses that exact pair (`bg-accent border-accent-foreground/30 text-accent-foreground`) rather
than inventing a second notice family. **Found and left alone**: the banner's own copy, "Platform
Admin – Super-administrator access only", is hardcoded English, not routed through next-intl — a
real, pre-existing gap this ADR does not fix, because this decision is about colour and
`web/messages/*.json` is fenced to other agents this batch.

### 5. Stat cards: an arbitrary rotation is decoration — four files

`platform/metrics/page.tsx` (five tiles: blue, purple, rose, green, plus one already-`accent`
entry) and `(dashboard)/dashboard/page.tsx` (four quick-link icons: blue, green, purple, plus one
already-`accent` entry) each assign a distinct hue per item with no relationship to any item's
state, severity, or value — a metric count going up or down does not change which colour its tile
gets. That is decoration, not information, so the answer here is the seed's own third option:
**both collapse onto the single `accent`/`accent-foreground` pair every set already used for at
least one of its own members.** This also brings `(dashboard)/dashboard/page.tsx` in line with
`backoffice/dashboard/page.tsx`, whose four stat-icon tiles were already uniform `bg-accent
text-accent-foreground` before this ADR — the inconsistency was that two dashboards disagreed
with each other, and now they do not.

Two entries in this group are **not** decorative rotation and are decided separately:

- **`platform/clans/page.tsx`'s active/suspended badge** (`bg-green-100 text-green-700` active)
  is a real two-state status, and its text already says which state ("Hoạt động" / "Tạm ngưng"),
  so — like the approve button above — colour reinforces rather than carries it. It takes the new
  `success` token: `bg-success/10 text-success`, mirroring the same `/10`-opacity shape
  `RoleSelector`'s `admin` state already uses for `destructive`.
- **`backoffice/dashboard/page.tsx`'s trend line and badge** (`text-green-600`/`text-orange-600`,
  `bg-orange-500 text-white`) read a genuine positive/negative direction, and the change text
  itself already names the direction ("+12 this month" vs "3 new today"). Positive takes
  `text-success`; negative takes the already-gated `text-destructive`; the notification-count
  badge takes `bg-destructive text-destructive-foreground`, reusing the "needs attention" reading
  `destructive` already carries for the reject button and the admin role state, rather than adding
  a solid warning-fill token nothing else needs yet. (This file's stats are its own comment's
  "intentionally static/mock for now" — the colour still has to work in both schemes regardless.)

## What was NOT added, and why

- **No `info` token family.** Spec § 2.1/2.2 publish one, but no second surface in this codebase
  needed it once `editor` was reconsidered as "the normal role" rather than "an informational
  state." Adding a family for one use is exactly the rot this ADR's own instructions warn against.
- **No `success-container` / `success-foreground`.** Every current use of `success` is plain text
  or a translucent (`/10`) fill; a solid-fill pairing is added the day a caller needs one.
- **No second channel (icon) for gender**, and no icon for event kind or role. Where colour was
  genuinely the only channel (gender), the fix is to remove the colour rather than add UI scope a
  decision seed should not take on. Where colour was already reinforcing text (role, event kind,
  status), no second channel was owed in the first place.
- **The minimap's own chrome** (background, `maskColor`) is not made theme-aware. `@xyflow/react`
  props are plain strings, not tokens, and building a JS-side bridge to the colour-scheme media
  query would be this codebase's first departure from ADR-045's "never branch on theme in
  TypeScript" rule — a materially larger, separate decision.
- **The hardcoded English banner string** in `platform/layout.tsx` is left as found. It is a real
  `T-12`/localisation gap, not this ADR's to fix.

## Verification

**The full web gate** (`web/CLAUDE.md`), run 2026-08-22:

- `pnpm type-check` — clean.
- `pnpm lint` — clean (empty output).
- `pnpm format:check` — clean, after one `pnpm exec prettier --write` on the single file its own
  edit misformatted (`backoffice/dashboard/page.tsx`).
- `pnpm depcruise` — 0 errors, 3 warnings (the same three pre-existing orphans the persons slice and the sweep
  recorded; unaffected by this change).
- `pnpm test:unit` — 430 passed, including `contrast.test.ts`'s new `success` rows and
  `theme-tokens.test.ts`'s automatic coverage of the new token, both added by this change.
- `pnpm test:component` — 51 passed.
- `pnpm test:e2e` — 58 passed (unchanged from before this seed: none of the two public routes that
  suite reaches render any of the ten converted files).
- `pnpm build` — see the commit's own gate run for the final combined number.

**`success`'s contrast, measured 2026-08-22 by running `contrast.test.ts`'s own algorithm (WCAG
2.1 relative luminance) against `globals.css`'s literal values, against all three grounds, both
schemes:**

| Scope | `success` hex | vs `card` | vs `background` | vs `muted` |
|---|---|---|---|---|
| light | `#2e6a4e` | 6.39:1 | 6.02:1 | 5.80:1 |
| dark | `#8fcfaa` | 9.57:1 | 10.25:1 | 8.85:1 |

All six clear the 4.5:1 AA floor `contrast.test.ts` enforces; `pnpm test:unit` re-runs this exact
computation from the stylesheet on every run, so this table is a record of one measurement, not a
second source of truth.

**The negative control the seed asked for, run 2026-08-22.** None of the ten converted files sit
on a route `web/e2e/dark-theme.spec.ts` (or any existing e2e spec) can reach: `RoleSelector` and
`PendingUsersList` render only under `admin/*`, `EventCard` under `events/*`, `MemberNode` /
`MemberAvatar` under `tree/*` and `members/*`, and the four dashboard/platform files under
`(dashboard)`, `platform/*`, and `backoffice/*` — every one of them gated by
`requireServerRole`/`requireRole` behind a real Supabase session that this repository's e2e
harness does not fake. **This is the exact finding ADR-046 recorded for `BackofficeSidebar.tsx`**,
re-confirmed here for a second, larger set of files: "say how you measured it rather than
reasoning from the hex values," because the seed's own verification text ("an
`e2e/dark-theme.spec.ts` case per converted surface") assumes a reachability this tree does not
have.

Measured instead with the same throwaway-preview-route technique the persons form
used for `StaleWriteDialog` ("rendered directly with fixture rows, no backend, deleted before this
commit"): a temporary route rendering `RoleSelector`, `PendingUsersList`, and `MemberAvatar` with
fixture props, with `NEXT_PUBLIC_SUPABASE_URL`/`_ANON_KEY` unset so `src/middleware.ts` skips its
session check, driven by a real Chromium instance with `page.emulateMedia`. Both the route and the
throwaway spec were deleted before this ADR's commit; the readings:

| Element | Reads | Light | Dark |
|---|---|---|---|
| `RoleSelector`'s `editor` pill | `background-color` | `rgb(214, 228, 206)` (`#d6e4ce`, `primary-container`) | `rgb(43, 69, 38)` (`#2b4526`, dark `primary-container`) |
| `PendingUsersList`'s approve button | `color` | `rgb(46, 106, 78)` (`#2e6a4e`, `success`) | `rgb(143, 207, 170)` (`#8fcfaa`, dark `success`) |
| `MemberAvatar`'s fill (`gender="male"`) | `background-color` | `rgb(243, 244, 246)` (`#f3f4f6`, `muted`) | `rgb(36, 34, 26)` (`#24221a`, dark `muted`) |

All three flip between schemes and match the tokens named above exactly.

**The planted defect, on the `editor` pill, the same element measured above.** `RoleSelector.tsx`'s
`editor` entry was reverted to the pre-fix `'bg-blue-50 text-blue-700 border-blue-300'`, the same
preview route reloaded under both emulated schemes, and reverted back immediately after reading:

| Reading | Light | Dark |
|---|---|---|
| Fixed (`primary-container`) | `rgb(214, 228, 206)` | `rgb(43, 69, 38)` — **differs** |
| Planted defect (`bg-blue-50`) | `lab(96.492 -1.14644 -5.11479)` | `lab(96.492 -1.14644 -5.11479)` — **identical** |

The planted-defect reading is identical across both emulated colour schemes, which is exactly the
failure this whole seed exists to catch — a palette colour that cannot flip — and it is a
different value from the passing reading in both directions, so this is a real control per
`.claude/rules/testing.md`'s "check that the failing reading differs from the passing reading."

**What this does not prove.** The other seven converted files (`MemberNode`, `EventCard`,
`platform/layout.tsx`, both stat-tile files, `platform/clans/page.tsx`,
`backoffice/dashboard/page.tsx`) were not individually re-rendered in a browser. Every one of them
composes the same small set of tokens verified above (`border-border`/`bg-muted`, `accent`/
`accent-foreground`, `success`, `destructive`/`destructive-foreground`) and was read at source
(`grep`/`Read`) to confirm the class names are exactly the tested ones — but "the class is spelled
correctly in the source" and "a browser applies it as expected" are different claims, and only the
three rows above are the second kind.

## Related

- The palette sweep, which found the 41-plus-3 and refused to invent values for them.
- [ADR-045](045-dark-mode-prefers-color-scheme-only.md), for the one mechanism and the "never
  branch on theme in TypeScript" rule this ADR does not relax for `TreeCanvas.tsx`'s minimap.
- [ADR-046](046-backoffice-aside-is-a-surface-step-not-an-inverted-region.md), for the
  "say how you measured it" precedent this ADR follows for every gated surface.
- `docs/superpowers/specs/2026-08-02-design-system-and-screens.md` § 2.1 (light tokens, including
  `success`/`danger`/`info`), § 2.2 (dark tokens), § 5 `T-06` (colour is never the only channel),
  § 7.8 (event card layout, showing the type chip every kind already carries).
- `.claude/rules/tailwind.md` § 2 (token resolution, gated by `theme-tokens.test.ts`) and § 9
  (the accepted raw-hex exception for `@xyflow/react` props, which this ADR narrows rather than
  widens for `TreeCanvas.tsx`).
