# ADR-041: Leaf Green Is `primary`, Lacquer Red Becomes the `heritage` Family, and One Warm Ground Is `background`

## Status

Accepted (2026-08-14). **Not shipped.** `web/` still paints the red on every screen. Seed S-005
does the rename, and this ADR is the authority it reads.

## Context

Two documents disagree about what the primary colour of this product is, and the disagreement has
been open since the design spec was written. Seed S-004 exists to close it. Nothing here is a new
idea: the spec already argued its side, and this ADR records that the argument won, plus four
things the spec does not say and one thing the spec gets wrong.

### Three primaries are live in the tree, not two

Every value below was read on 2026-08-14.

| Where | Source | Value |
|---|---|---|
| web | `web/src/app/globals.css:16`, `--color-primary` | `#c41e3a` lacquer red |
| the spec | `docs/superpowers/specs/2026-08-02-design-system-and-screens.md` § 2.1, `primary` | `#3E5C38` leaf green |
| mobile | `mobile/lib/core/theme/tokens.dart:32`, `primary` | `#7A5C2E` bark bronze |

**Spec § 9-J1 is stale about the third one.** It says mobile "declares a green primary twice, at
two different values", naming `mobile/lib/app/theme/colors.dart` `#4A6741` and
`mobile/lib/core/theme/app_colors.dart` `#37563B`. `ls` finds neither file on 2026-08-14. ADR-034
deleted both in the Riverpod rebuild, which § 9-J1 itself predicted it would. What replaced them is
a single `ArborTokens.light()` factory whose `primary` is a bronze, so the spec's own conclusion,
that mobile has no single green to reconcile, is still true, but for a different reason than the
one written down. Read `tokens.dart`, not § 9-J1, for what mobile holds.

### The token the conflict is about paints nothing

This is the fact that changes the shape of the work, and no earlier document records it. Counted
across `web/src` on 2026-08-14, excluding `globals.css`:

- `bg-primary`, `text-primary`, `text-primary-foreground`, `ring-ring`, `bg-secondary`,
  `bg-background`, and `bg-card` appear **zero** times.
- The indexed ramp appears **78** times across **20** files.

| Class | Uses | Class | Uses |
|---|---|---|---|
| `ring-primary-500` | 28 | `bg-primary-50` | 3 |
| `bg-primary-600` | 10 | `ring-primary-400` | 2 |
| `bg-primary-700` | 9 | `text-primary-400` | 1 |
| `text-primary-700` | 8 | `border-primary-500` | 1 |
| `text-primary-600` | 7 | `border-primary-300` | 1 |
| `bg-primary-100` | 4 | `accent-primary-600` | 1 |
| `border-primary-400` | 3 | | |

So `--color-primary` at `globals.css:16` is the token that generates `bg-primary`, exactly as spec
§ 2.8.1 D says, and `bg-primary` is used by nothing. **Renaming that one line repaints zero
pixels.** What is red on screen is the nine-entry ramp at `globals.css:6-15`. Any decision that
moves `primary` and leaves the ramp alone changes nothing a user can see.

### Two names for the background, and the two other clients name two more

`--color-cream: #fdfbf7` at `globals.css:44` is what `body` paints, through `@apply bg-cream` at
`:189`. `--color-background: #f8f4ec` at `:65` is what the semantic token calls the page. The dead
`:root --cream: #f8f4ec` at `:177` is a third label on the second value. Both values also sit in
the cream ramp, at `:39` and `:40`.

Neither value is the spec's. Spec § 2.1 names the page ground `surface` `#FBF8F1`. Mobile names it
`surface` `#FDFCF7` (`mobile/lib/core/theme/tokens.dart:29`). Four near-identical warm whites, one
page.

### Why the spec's side wins

Spec § 2.8.1 D states its own conclusion plainly: "This document is correct and the app is the
bug." The reasoning is § 2.1's and § 9-J1's, and it is not about taste. A red-dominant interface
reads as alarm in a product whose most common actions are neutral, and red has to stay affordable
for two other jobs: ceremonial emphasis (thủy tổ, giỗ) and destructive confirmation. Spending it on
ordinary buttons is what makes it stop meaning anything. `destructive` is already `#a32218` and
`heritage` is `#a3182f`, one digit apart, so with a red `primary` the palette would carry three
reds doing three different jobs at nearly the same value.

## Decision

Five parts. The first four are the four questions seed S-004 asks. The fifth is forced by the
first, and is recorded here rather than left to S-005 for the reason given under it.

### 1. `primary` is leaf green `#3E5C38`

The spec's value, exactly. `primary-foreground` stays `#ffffff`.

Bronze `#7A5C2E` was the one alternative with a real argument, because it would make web and mobile
agree today with no mobile change. It is rejected: it collides with `secondary` `#7a6248`, which is
also a bark brown and shares its red channel exactly, so the palette would carry two browns doing
two jobs.
The leaf-green reading is also what makes `heritage` legible as a separate family rather than as a
second accent.

### 2. `heritage` becomes a four-token family

All four values are spec § 2.1's, taken exactly:

| Token | Value | Use |
|---|---|---|
| `heritage` | `#A3182F` | Thủy tổ marker, giỗ, ancestral emphasis |
| `heritage-foreground` | `#FFFFFF` | Text and icons on `heritage` |
| `heritage-container` | `#F6DFE0` | Giỗ chips, thủy tổ card ground |
| `heritage-container-foreground` | `#4A0A14` | Text on `heritage-container` |

The spec spells the last two `on-heritage` and `on-heritage-container`. **This ADR keeps the
repository's existing `-foreground` suffix** rather than importing the spec's `on-` prefix, because
every one of the seventeen semantic tokens in `globals.css` already uses `-foreground`, and one
family spelled differently from the other sixteen is a trap for the next reader. The values are the
spec's; only the spelling is the repository's.

The container pair ships now rather than when a screen needs it. Deferring it is what put red in
`primary` in the first place: a marker with no token gets the nearest token instead.

### 3. `background` is `#FBF8F1`, one value under one name

The spec's `surface`. Both existing values die. `--color-cream` is removed and `body` paints
`bg-background`. The dead `:root --cream` at `globals.css:177` is removed with the rest of that
block.

This is the answer S-004 did not offer, and it is worth saying why a third value beats either
incumbent. `#fdfbf7` is what is on screen but nothing sources it. `#f8f4ec` is what the token says
but nothing paints it. Picking either means the app and the spec still disagree about the page
ground, and the next agent has to re-open this. Picking the spec's value settles it in the same
direction as decision 1, which is the whole point of writing one ADR rather than four.

**The cream *ramp* stays.** `cream-50` through `cream-400` are used 17 times across 7 files, mostly
as `border-cream-200`, and this ADR does not touch them. Only the bare `--color-cream` goes.

### 4. The rename lands in one change

Seed S-005 as written, one pull request, all 78 ramp occurrences plus the 8 screen uses of
`bg-cream`. Not per feature slice.

A per-slice rollout was considered seriously, because these files are the frozen legacy tree that
`web/CLAUDE.md` says is being deleted slice by slice, so a rename spends work on code scheduled to
die. It is rejected on one ground: for the length of the migration the app would paint red and
green at once, on adjacent screens, and there is no gate that can see that. A design system whose
current value depends on which slice you are looking at is not a design system.

### 5. The nine-step ramp is deleted, and the focus ring stops being an accent

This is not a fifth question. It is what decision 1 means in the file, and leaving it out would
hand S-005 a decision it cannot make from its own sources: nine red values with no green
replacement written anywhere. Spec § 2.1 publishes no nine-step green ramp, so an agent asked to
"rename primary to green" would have to invent eight values. It should not.

**Replace the ramp with the spec's tonal set.** Four tokens carry every job the thirteen ramp
classes are doing today:

| Ramp classes today | Becomes | Value |
|---|---|---|
| `bg-primary-600`, `bg-primary-700` (19 uses) | `bg-primary` | `#3E5C38` |
| `text-primary-600`, `text-primary-700`, `text-primary-400` (16 uses) | `text-primary` | `#3E5C38` |
| `bg-primary-50`, `bg-primary-100` (7 uses) | `bg-primary-container` | `#D6E4CE` |
| `border-primary-300/400/500` (5 uses) | `border-primary` or `border-primary-container` | per site |
| `ring-primary-400`, `ring-primary-500` (30 uses) | `ring-ring`, see below | `#1D1B16` |
| `accent-primary-600` (1 use, `TreeControls.tsx:52`) | `accent-primary` | `#3E5C38` |

The six rows account for all 78. The last is a native `accent-color` on a range input, not a
Tailwind semantic, and it is listed so that a rename which greps for `bg-`/`text-` does not miss it.

`primary-container` is `#D6E4CE` and `primary-container-foreground` is `#14260F`, both spec § 2.1,
respelled per decision 2.

**Hover and pressed are derived, not tokens.** Spec § 4.1, line 582, already specifies them: hover is
the fill darkened 6% on light, pressed is darkened 12%. That is why `bg-primary-700` does not need
a green twin. Express the state as a darkening of `primary`, not as a second hex.

**`--color-ring` becomes `#1D1B16`, not the new primary.** Spec § 2.1 makes the focus ring the
on-surface colour rather than an accent, at 3px with a 2px `surface`-coloured offset. The reason it
gives is sound and the measurement below shows why an accent ring cannot work: today's red ring on
a green button would measure 1.29:1.

## What was measured, and the one spec claim that does not reproduce

Computed 2026-08-14 with the WCAG 2.1 relative-luminance formula, on the ground set this ADR
creates: `card #ffffff`, `background #FBF8F1`, `muted #f3f4f6`. `cream` is gone, so it is not a
ground any more.

**Text, floor 4.5:1.** Worst of the three grounds.

| Foreground | card | background | muted | Worst |
|---|---|---|---|---|
| `primary` `#3E5C38` | 7.52 | 7.09 | 6.83 | **6.83** |
| `heritage` `#A3182F` | 7.70 | 7.26 | 6.99 | **6.99** |
| `foreground` `#1a1a1a` | 17.40 | 16.41 | 15.81 | **15.81** |
| `muted-foreground` `#6e6653` | 5.69 | 5.37 | 5.17 | **5.17** |
| `destructive` `#a32218` | 7.50 | 7.07 | 6.82 | **6.82** |
| `secondary` `#7a6248` | 5.72 | 5.40 | 5.20 | **5.20** |

**Fixed pairs, floor 4.5:1.**

| Pair | Ratio |
|---|---|
| `primary-foreground #ffffff` on `primary #3E5C38` | 7.52 |
| `primary-container-foreground #14260F` on `primary-container #D6E4CE` | 12.06 |
| `heritage-foreground #ffffff` on `heritage #A3182F` | 7.70 |
| `heritage-container-foreground #4A0A14` on `heritage-container #F6DFE0` | 12.31 |

**Boundaries, floor 3:1.** `ring #1D1B16` measures 17.20, 16.22, and 15.63 over the three grounds.
`input #8a8072` measures 3.88, 3.66, and 3.53.

Contrast did not decide question 1. Red `#c41e3a` also clears AA in both directions (5.84 on card,
5.84 for white on it). The green wins on the argument, not on the numbers, and it is worth saying
so plainly rather than dressing a preference as a measurement.

### Spec § 2.1's justification for the focus ring is wrong, and the decision survives it

Spec § 2.1 says of `focus-ring #1D1B16`: "Using on-surface rather than an accent guarantees ≥3:1
against every ground in the system, **including `primary` and `heritage` fills**." Measured
2026-08-14:

| Pair | Ratio | Against the claim |
|---|---|---|
| `#1D1B16` on `primary #3E5C38` | **2.29** | fails |
| `#1D1B16` on `heritage #A3182F` | **2.24** | fails |
| `#1D1B16` on `destructive #a32218` | **2.29** | fails |
| `#1D1B16` on `secondary #7a6248` | 3.01 | passes, barely |

The sentence is false as written. The decision still holds, because the spec's *other* half saves
it: the ring ships "with a 2px `surface`-coloured offset", so the colour adjacent to the ring is
the offset, not the fill, and against `background` the ring measures 16.22. **The offset is
therefore load-bearing, not decoration.** A focus ring drawn directly on a filled button, with no
offset, is non-compliant at 2.29:1 whatever this ADR says. S-005 must ship the offset with the
ring.

An accent ring is worse in every direction and is not the fix: today's `#c41e3a` on the new green
fill measures 1.29:1.

## Consequences

### What seed S-005 must do

1. Replace the nine `--color-primary-*` entries at `globals.css:6-15` and the bare
   `--color-primary` at `:16` with `primary`, `primary-foreground`, `primary-container`, and
   `primary-container-foreground`.
2. Add the four `heritage` tokens.
3. Set `--color-background: #FBF8F1`, remove `--color-cream`, and change `@apply bg-cream` at
   `:189` to `bg-background`. Eight screen uses of `bg-cream` move with it: `login/page.tsx:44`,
   `pending-approval/page.tsx:12`, `register/page.tsx:100` and `:114`,
   `(dashboard)/layout.tsx:41` and `:50`, `tree/page.tsx:16`, `select-clan/page.tsx:49`.
4. Set `--color-ring: #1D1B16` and ship the 2px offset with it.
5. Delete the dead `:root` pair at `:174-175` and `--cream` at `:177`.
6. Update `.claude/rules/tailwind.md` § 2. Both of its lists go stale: the "these classes work now"
   list names `bg-primary` and the `primary-50` to `primary-900` ramp, and the "not fixed" list
   names this conflict as open.

### What breaks loudly, on purpose

`web/src/app/contrast.test.ts` will fail the moment `--color-cream` is removed. Its `GROUNDS`
constant lists `cream`, and its `token()` helper throws rather than returning `undefined` when a
name is missing. That is the behaviour S-003 built on purpose. S-005 updates `GROUNDS` to the three
grounds above and adds rows for every token this ADR creates.

**Two rows must not be added.** `primary-container` and `heritage-container` are grounds, not
boundaries. Sweeping them against the page at 3:1 measures 1.20 and fails, and that failure would
be meaningless: WCAG 1.4.11 governs boundaries and meaningful graphics, not the ground colour of a
tonal card. They enter the table as the `on` side of a pair, under their own `-foreground`, never
as a swept foreground.

### Mobile still disagrees, and this ADR does not fix it

`mobile/lib/core/theme/tokens.dart:32` holds `#7A5C2E`. This ADR binds both clients, because the
Arbor Heritage mandates bind both and a design system that is true on one client is not a design
system. But S-005 is web-only by its own text, and aligning `ArborTokens` is a Flutter change under
a different quality gate. It is **seed S-037**, allocated here, and it is not blocked by S-005:
both read this ADR, and neither reads the other.

Until S-037 lands, mobile and web paint different primaries, and that is a known open state rather
than an oversight.

### What this ADR deliberately does not decide

- **The dark palette.** Spec § 2.2 holds it. Seed S-006 owns it, and § 2.8's
  `prefers-color-scheme` versus `data-theme` contradiction with `globals.css:3` goes with it.
- **The cream ramp**, `cream-50` to `cream-400`, 22 uses. Untouched.
- **`foreground #1a1a1a` versus the mandate's `#1d1b16`.** Two near-identical near-blacks, and the
  mandate in `mobile/CLAUDE.md` names the second. Real, small, and not this ADR's question.
- **`muted #f3f4f6`**, a cool grey among warm grounds. Same reason.
- **Which screens compose which token.** Seed S-035 owns moving forms off `border-gray-300`.
- **Whether `--font-serif` should be renamed**, which `globals.css:104` already flags.

## Related

- Seed S-004 in [`../SEEDS.md`](../SEEDS.md), which this ADR closes; seed S-005, which implements
  it; seed S-037, which this ADR creates.
- [`../superpowers/specs/2026-08-02-design-system-and-screens.md`](../superpowers/specs/2026-08-02-design-system-and-screens.md)
  § 2.1 for every value taken here, § 2.8.1 D and E for the conflict, § 4 line 582 for the hover
  and pressed derivation, § 9-J1 for the three-primaries argument and for the stale mobile paths.
- [ADR-034](034-mobile-riverpod-rebuild.md), which deleted the two mobile theme files § 9-J1 names.
- [`../../.claude/rules/tailwind.md`](../../.claude/rules/tailwind.md) § 2, which requires this ADR
  before a token moves, and which S-005 updates.
- `web/src/app/contrast.test.ts`, the gate that holds these values.
