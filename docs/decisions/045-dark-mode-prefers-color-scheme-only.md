# ADR-045: Dark Mode Switches on `prefers-color-scheme` Alone, and the Dark Palette Is a Token Override

## Status

Accepted (2026-08-21). **Shipped in the same change**, by seed S-006. `web/src/app/globals.css`
carries the palette, `web/src/app/contrast.test.ts` gates its ratios in the unit suite, and
`web/e2e/dark-theme.spec.ts` measures the flip in a real browser.

**The palette is shipped and most screens are not dark yet.** That is a stated consequence, not
an oversight. Read "What this decision does not buy you" before reporting it as a defect.

## Context

Three mechanisms were declared for one behaviour, and each of the three had a document behind it.

| Mechanism | Where it came from | State on 2026-08-21, before this ADR |
|---|---|---|
| `@custom-variant dark (&:is(.dark *))` | `web/src/app/globals.css:3`, written before the design spec existed | declared; nothing in `web/src` ever set the class |
| `@media (prefers-color-scheme: dark)` | design spec § 2.8 | not present |
| `:root[data-theme="dark"]` | design spec § 2.8, in the same sentence | not present |

Spec § 2.8 asks for the second **and** the third. `globals.css:3` shipped the first. ADR-041 read
the conflict and declined to settle it, in its own words: the dark palette and "§ 2.8's
`prefers-color-scheme` versus `data-theme` contradiction with `globals.css:3` goes with it",
handed to seed S-006. `.claude/rules/tailwind.md` § 3 says the same, and adds the rule that a
component must never settle it.

Two measurements decide the question, and both were taken on 2026-08-21 in `web/`:

- **`grep -rn 'dark:' src` returns 0.** No `dark:` utility exists, so no existing screen depends
  on which mechanism the variant uses. Nothing regresses whichever way this goes.
- **A theme switch does not exist.** No file sets a class or an attribute on the document
  element, and `e2e/dark-theme.spec.ts` now asserts that none does.

That second one is what makes the choice one-sided rather than a matter of taste. A class
mechanism and an attribute mechanism are both *inert until something sets the marker*, and the
thing that sets it is a theme switch. Seed S-006 excludes a switch by its own text. So either of
those two would have shipped a full palette that never activates on any device — thirty
declarations of dead CSS, in a repository whose last five seeds were spent removing exactly that
class of defect. Seventeen dead tokens (S-001), two dead font families (S-002), a dead `--primary`
pair (S-005).

## Decision

### 1. The colour-scheme media query is the mechanism, and it is the only one

`globals.css` carries one dark scope, an unlayered `@media (prefers-color-scheme: dark)` block
holding a `:root` rule. The class variant on line 3 is **deleted**, and no `data-theme` selector
is introduced.

Deleting line 3 is not merely tidying: the Tailwind v4 default `dark:` variant *is* the media
query, so removing the override makes the default the decision. A `dark:` utility and the palette
now switch on the same signal. Nobody has to remember which.

`contrast.test.ts` holds all three halves of this: the media query appears exactly once, the
string `.dark` appears nowhere, and the string `data-theme` appears nowhere. The check reads the
stylesheet with comments stripped, so `globals.css` stays free to *name* the two rejected
mechanisms in prose while being unable to *use* them.

### 2. The block is unlayered, and that is load-bearing

`@theme` emits its variables into `@layer theme`. Unlayered CSS beats every layer, so the dark
block wins wherever it sits in the file. Put it inside `@layer base` or `@layer utilities` and it
loses to `@theme`, the app stays light, and **nothing anywhere reports an error**. That is why
`e2e/dark-theme.spec.ts` exists: a stylesheet can show you both declarations and cannot tell you
which one won.

### 3. The palette redefines only `--color-*`, and no component branches

Every Tailwind utility reads its colour through the variable, so overriding the variable flips
`bg-card`, `text-muted-foreground`, and the rest with no `dark:` utility and no TypeScript. That
is spec § 2.8's rule, "components never branch on theme themselves", and
`.claude/rules/tailwind.md` § 3's rule that the theme is a CSS concern.

Twenty-five tokens are overridden: the seventeen semantic names, the four-token `primary` family,
and the four-token `heritage` family. Values come from spec § 2.2 except where marked derived
below. Every pair is measured by `contrast.test.ts`, which runs its whole table twice, once per
theme; zero pairs fail, and the worst dark ratio is 6.07:1 against a 4.5 floor and 6.07 against a
3 floor.

### 4. Five values are derived rather than quoted, and one departs from the spec

Spec § 2.2 does not publish an "on" colour for its dark status or `heritage` fills, and it does
not publish a default border for either theme. So:

| Token | Dark value | Why it is not a quote |
|---|---|---|
| `heritage-foreground` | `#4e1520` | § 2.2 gives no dark `on-heritage`, and the fill `#f0a0a8` is light, so a white label fails. Takes the container ink. 7.09:1 |
| `secondary-foreground` | `#2a2013` | § 2.2 gives no dark `on-secondary`. Takes light's `on-secondary-container`. 8.72:1 |
| `destructive-foreground` | `#4a1811` | § 2.2's status line gives `danger #F0A79C / #4A1811`, a token and a container. The ink on the fill is the container value. 7.49:1 |
| `border` | `#2d2a20` | § 2.1 reserves `outline-variant` for high-contrast mode at 15% opacity, so no default border is published. This is `surface-container-high` used as a background step, keeping the no-line rule. 1.11 to 1.29, against light's 1.13 |
| `accent` / `accent-foreground` | `#3e2a06` / `#e8b563` | `accent` is a shadcn leftover ADR-041 left undecided. Light uses it as a warning *container* under a warning ink, so dark takes § 2.2's dark warning pair in that order. 7.29:1 |

**And one deliberate departure.** `card` and `popover` take `surface-container-low` `#1d1b15`,
not `surface-container-lowest` `#100f0b`. Spec § 2.1 labels `surface-container-lowest` "cards that
must lift off the page", and in light it is `#FFFDF9`, lighter than the page. In dark, § 2.2 makes
it `#100f0b`, *darker* than `surface` `#15140f`, so the same role would make a card read as
recessed. A role names a relationship, so this keeps the relationship and changes the value. The
spec owns its own table and may overrule this; if it does, the value moves here and in
`globals.css` together.

### 5. The dark hover fill names a literal hex, and the gate is why that is allowed

Spec § 4.1 line 582 gives both halves of the hover treatment: the fill is "darkened 6% (light) /
**lightened 8% (dark)**". S-005 implemented the light half only, because light was all it needed.
So dark mixes white where light mixes black.

The awkward part is the base. Light writes `color-mix(in oklab, var(--color-primary) 94%, black)`,
one value in one place, which is ADR-041 § 5's rule. Dark writes the hex literally. **Measured on a
production build, 2026-08-21:** with `var(--color-primary)` inside the dark block, Lightning CSS
resolved the `var()` against the top-level `:root` when emitting the pre-`color-mix()` sRGB
fallback, so the dark fallback came out `#4d6948` — the *light* primary lightened — and
`primary-foreground` `#12280d` on it measures **2.57:1**. Every browser with a dark preference and
no `color-mix()` support, roughly 2019 to 2023, got an unreadable hover label in dark, and no
source-level check could see it. With the literal, the same build resolves the mix outright to
`#aac8a0`, emits no fallback branch at all, and the label measures **8.60:1**.

So the literal is accepted, and the duplication it creates is gated rather than trusted:
`contrast.test.ts` fails when the hex inside the mix stops matching the token above it.

### 6. The gold and cream ramps stay theme-invariant

Neither appears in the dark scope. They are palette ramps rather than semantic roles, ADR-041
explicitly leaves the gold family undecided, and § 2.2 keeps `gilt-decor` at `#d4af37` in both
themes. Inventing a nine-step dark gold is the mistake ADR-041 refused when it deleted the red
ramp rather than recolouring it.

## Consequences

### What this decision buys

- Dark mode works today, on every device whose OS asks for it, with no JavaScript, no hydration
  step, and no flash of the wrong theme.
- A screen built on tokens is dark-correct for free. A `dark:` utility, if one is ever needed,
  switches on the same signal as the palette.
- Two gates now fail on a class of defect that previously passed: a dark pair below AA, and a dark
  palette that does not reach the page.

### What this decision does not buy you, stated plainly

**A user cannot override their operating system.** That is the real cost, and it is the whole cost.
Someone on a light OS who wants a dark app, or the reverse, has no control. A theme switch is a
reasonable want; it revisits this ADR rather than adding a fourth mechanism beside it, and adding
one is a seed with an ADR of its own.

**Most screens are not dark yet.** Counted in `web/src` on 2026-08-21: **393 hardcoded palette
utilities across 41 files** — `text-gray-*` 187, `border-gray-*` 82, `bg-gray-*` 33,
`divide-gray-*` 2, and 89 more in the red, amber, blue, green, purple, rose, pink, and orange
families. A palette colour is not a token and has no dark value, so none of them flips. Seed
S-038 owns moving them. Until it lands, the palette is correct and the screens built on Tailwind's
own greys are not, and a screenshot in dark mode will show that.

**The backoffice aside is still hand-built.** `web/src/components/backoffice/BackofficeSidebar.tsx:30`
is `bg-gray-950` `#030712`, and after this change it sits at `#030712` against a `#15140f` page,
so the boundary between the aside and the content nearly vanishes in dark. Expressing it properly
needs an inverse-surface role that neither § 2.1 nor § 2.2 publishes, which is a decision rather
than an edit. Seed S-039 owns it.

**Two raw hexes remain in `globals.css`**, the scrollbar thumb `#d1d5db` and its hover `#9ca3af`.
Both stay visible on a dark ground, so this is untidiness rather than a defect. S-038 takes them.

### What changed outside the palette

Two lines in `globals.css` had to move for the palette to mean anything, and both are small:

- **`body` now applies `text-foreground`, not `text-gray-900`.** This is the line that decided
  whether dark mode worked at all: `body` painted the page with a token and its text with a
  Tailwind grey, so the ground flipped and the ink did not. Measured 2026-08-21 in Chromium under
  an emulated dark scheme, body text computed to `lab(8.11897 0.811279 -12.254)`, which is
  gray-900 `#111827`, on the new `#15140f` page. In light this moves body text from `#111827` to
  `#1a1a1a`; both clear AA on all three grounds.
- **The Tailwind v3 border shim now points at `var(--color-border)`, not `var(--color-gray-200)`.**
  The `*` rule further down applies `border-border` and covers elements, but not the four
  pseudo-element selectors the shim lists, which were painting a grey with no dark value. In light
  the two colours are the same to the eye, `#e5e7eb` both.

## What this ADR deliberately does not decide

- **A user-facing theme switch**, and therefore whether a `data-theme` attribute returns later as
  an override *on top of* the media query. That is a change to this decision, made deliberately.
- **Moving the 393 palette utilities onto tokens.** Seed S-038.
- **The backoffice aside, and whether an inverse-surface role exists.** Seed S-039.
- **A high-contrast mode.** Spec § 2.1 reserves `outline-variant` for one, and nothing else about
  it is settled.
- **The gold family**, still open from ADR-041, and therefore `gilt` `#8a6a16` still has no token
  in either theme.
- **Whether `accent` should be renamed** to say it is a warning container. This ADR maps it
  without renaming it, because a rename touches every use.

## Related

- Seed S-006 in [`../SEEDS.md`](../SEEDS.md), which this ADR closes; seeds S-038 and S-039, which
  it creates.
- [ADR-041](041-primary-green-heritage-family-single-background.md), which decided the light
  palette and handed this question here. Its § 5 is the one-value rule that § 5 above bends, under
  a gate.
- [`../superpowers/specs/2026-08-02-design-system-and-screens.md`](../superpowers/specs/2026-08-02-design-system-and-screens.md)
  § 2.2 for every quoted dark value, § 2.8 for the two mechanisms it asks for and the
  no-branching rule, § 2.8.1 B for the measurement that found the dark theme missing, § 4.1 line
  582 for the hover directions.
- [`../../.claude/rules/tailwind.md`](../../.claude/rules/tailwind.md) § 3, rewritten by this
  change from "declared but not built" to what is now true.
