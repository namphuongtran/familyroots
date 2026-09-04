# ADR-046: The backoffice aside stops being inverted and becomes a surface step

## Status

Accepted (2026-08-22). **Decision only. No file under `web/` changes in this
commit**, so no gate was run beyond the measurements recorded below. The edit this decision
requires is a follow-up change, specified in "What has to change" and sized so that one agent can land it.

**A live accessibility failure is recorded here and is not fixed here.** The backoffice brand mark
measures **1.90:1** under a dark colour scheme, measured in Chromium on 2026-08-22. Read "The
defect this uncovered" before reading anything else.

## The decision, in one sentence

The aside stops being a permanently dark region. It takes `muted` as its ground and the ordinary
semantic tokens as its ink, so that it flips with the rest of the app, and the boundary between the
aside and the content is a background step rather than an inversion. **This is a design change to
the backoffice, and it is stated as one.**

## Context

### What the aside is today

`web/src/components/backoffice/BackofficeSidebar.tsx:30` is:

```
w-60 h-screen flex flex-col bg-gray-950 text-gray-100 shrink-0 fixed left-0 top-0
```

`bg-gray-950` is a Tailwind palette colour, not a token. It has no dark value, so it cannot flip.
Every other ink in the file is the same kind of value: `text-gray-100` at `:30`, `border-gray-800`
at `:32` and `:74`, `text-gray-400` at `:45`, `:62`, and `:77`. Two things in the file are tokens:
`text-primary-container` on the brand mark at `:42`, and `bg-primary text-primary-foreground` on the
active nav item at `:61`.

`bg-gray-950` is the only near-black ground in `web/src`. Checked 2026-08-22:
`grep -rn "bg-gray-9\|bg-black" web/src` returns three lines, and one of them is the comment at
`BackofficeSidebar.tsx:35` that describes the other two.

### The seed's central measurement does not reproduce, and the reason matters

This decision and ADR-045 both say the same thing. ADR-045, "What this decision does not buy you":

> `web/src/components/backoffice/BackofficeSidebar.tsx:30` is `bg-gray-950` `#030712`, and after
> this change it sits at `#030712` against a `#15140f` page, so the boundary between the aside and
> the content nearly vanishes in dark.

**The aside does not sit against the page.** Read at source on 2026-08-22,
`web/src/app/[locale]/backoffice/layout.tsx:32` paints the content beside it:

```tsx
<main className="ml-60 flex-1 min-h-screen overflow-y-auto bg-gray-50">
```

`bg-gray-50` is `#f9fafb`. It is a palette colour, so it does not flip either. The wrapper at `:30`
is `bg-gray-900`, also a palette colour, and it was not visible in the rendered probe because
`<main>` is `min-h-screen flex-1`.

So the backoffice has **two** hand-built grounds facing each other, not one hand-built ground facing
a token. Measured in Chromium on 2026-08-22, by reading pixels back from a screenshot of the real
compiled stylesheet: the aside is `#030712` and the content is `#f9fafb`, in **both** colour
schemes, and the step between them is **19.27:1** in both. The boundary is as strong as it ever was.

**The dark-palette change did not make the backoffice worse.** It did not change it at all, because nothing in
the backoffice reads a ground token. The one thing it did change is the next section.

**The prediction is right, one change early.** The palette sweep's end state is that no `-gray-`
utility remains in `web/src` outside `BackofficeSidebar.tsx`. `layout.tsx:30` and `:32` are inside
that sweep. The moment the sweep points `<main>` at `bg-background`, the aside `#030712` does sit
against the page `#15140f`, and that pair measures **1.09:1**. So the vanishing boundary is a real
future state with a named cause, rather than a present defect. **Whatever lands from this ADR must
land with or before the sweep's edit to `layout.tsx`**, or the backoffice gets a window in which the
rail and the page are the same darkness.

### The defect this uncovered

The brand mark at `BackofficeSidebar.tsx:42` is `text-primary-container`. That **is** a token, so it
flips, while the ground under it does not. The comment above it at `:33-41` records the reasoning
from 2026-08-14 and that reasoning has silently expired:

| Measured 2026-08-22, in Chromium | Light | Dark |
|---|---|---|
| ground under the mark (`bg-gray-950`) | `#030712` | `#030712` |
| mark (`text-primary-container`) | `#d6e4ce` | `#2b4526` |
| **ratio** | **15.19:1** | **1.90:1** |

15.19:1 reproduces the figure in the comment exactly. 1.90:1 is new, and it is well under the 4.5:1
floor and under the 3:1 non-text floor as well. The mark is close to invisible on a dark-preferring
device. It has been that way since the dark palette landed on 2026-08-21.

A second, smaller instance of the same shape: the active nav item at `:61` is `bg-primary`, and in
light `primary` `#3e5c38` against the ground `#030712` measures **2.68:1**. As a filled indicator
that tells a user which page they are on, WCAG 1.4.11 asks for 3:1 against what surrounds it. It
does not clear that. In dark, `primary` `#a3c398` clears it comfortably. Nobody had recorded this.

**Both failures have one cause, and it is not the value of any token.** A token was placed on a
ground that is outside the token system. Any token placed there fails in one theme or the other,
because the ink moves and the ground cannot.

### Why no gate saw either one

`web/src/app/contrast.test.ts` measures **token pairs** against three grounds, listed at `:168` as
`card`, `background`, and `muted`. `.claude/rules/tailwind.md` § 7 already states the limit in the
same words: "it checks token **pairs**, so a screen that puts `text-gray-500` on `bg-cream` is
invisible to it". `#030712` is not a token, so no case in that table can name it. `pnpm build`,
`pnpm type-check`, `pnpm lint`, and `pnpm depcruise` do not look at colour at all. This region has
never had a gate, and adding a token to `@theme` would not give it one either, for the reason in
option A below.

## The three options, and why two lost

### Option A: add an `inverse-surface` pair to `@theme` and gate it. Rejected.

**A1. Material 3's `inverse-surface` is not what this aside is, so the name would be wrong.**
Spec § 2 line 70 says "Naming follows Material 3 role naming". Read at source on 2026-08-22,
`/Users/southern/development/flutter/packages/flutter/lib/src/material/color_scheme.dart:1313-1316`
defines it:

> `/// A surface color used for displaying the reverse of what's seen in the`
> `/// surrounding UI, for example in a SnackBar to bring attention to`
> `/// an alert.`
> `Color get inverseSurface => _inverseSurface ?? onSurface;`

Two things follow from those four lines. The role is "the reverse of **what is seen in the
surrounding UI**", which is relative to the current theme, not absolute: its fallback is `onSurface`,
which is near-black in a light scheme and near-white in a dark one. And `onInverseSurface` falls back
to `surface` at `:1326`, which flips the same way. So an honest M3 `inverse-surface` would make this
aside **light** under a dark colour scheme, which is a second design change and a worse one: a
permanently pale 240px slab beside a `#15140f` page. Keeping the M3 name while giving it
"dark in both themes" semantics breaks the rule spec § 2 sets, and it does so in the one place a
future reader would trust the name.

The role's named use is also against it. M3 attaches it to a SnackBar, which is transient and small.
A full-height persistent rail is neither.

**A2. A pair is not enough, and the rest would have to be invented.** The aside carries a ground, a
primary ink, a secondary ink, a hover step, a boundary, a brand mark, and an active fill with its
own label. That is six roles at least. Spec § 2.1 and § 2.2 publish none of them, so all six would
be new values with no source. ADR-041 refused exactly this move when it deleted the nine-entry red
ramp rather than recolouring it, in its own words at `globals.css:20-27`: a recolour "would have
meant inventing eight values".

**A3. `contrast.test.ts` structurally rejects a token that does not flip, and that rejection is
correct.** Two cases stand in the way, and both were written with the dark palette to catch real defects:

- `contrast.test.ts:246-250`, "overrides every token this table measures", fails if a token named in
  `CASES` is absent from the dark scope.
- `contrast.test.ts:262-272`, "reads light and dark as two different palettes", fails if a dark
  override restates its light value.

A token whose whole purpose is to hold one value in both themes fails the first if it is not
overridden and the second if it is. Weakening either one to admit it would blunt the tripwire that
catches a parser reading the wrong palette, which was recorded as a defect that stayed **green**
under 156 passing cases. That price is too high for one region.

**A4. It would not fix the mark.** The 1.90:1 failure is `primary-container`, a token that flips.
Naming the ground does not stop the ink from moving under it.

### Option B: the aside stops being inverted. **Chosen.**

The ground becomes `muted`, which is spec § 2.1's `surface-container`, whose published job is
"grouped rows, list section grounds". A vertical list of navigation rows is that job. Every ink on
it then becomes a pair the gate already measures, because `muted` is one of the three grounds at
`contrast.test.ts:168`. Measured 2026-08-22:

| Pair | Light | Dark | Floor |
|---|---|---|---|
| `foreground` on `muted` (wordmark) | 15.81:1 | 13.41:1 | 4.5 |
| `muted-foreground` on `muted` (idle nav, sub-label, sign out) | 5.17:1 | 6.07:1 | 4.5 |
| `primary` on `muted` (brand mark, and the active fill as a boundary) | 6.83:1 | 8.20:1 | 4.5 |
| `primary-foreground` on `primary` (active nav label) | 7.52:1 | 8.10:1 | 4.5 |
| `input` on `muted` (any control boundary) | 3.53:1 | 6.07:1 | 3 |

Not one of those is a new row. All five are already in `CASES`, already run twice per theme, and
already green. **The whole region moves inside a gate that exists, at the cost of zero new tokens.**

The brand mark moves from `primary-container` to `primary`. That reverses the choice made on
2026-08-14, and it reverses it for the reason the comment at `BackofficeSidebar.tsx:33-41` named
itself: the ground. On the old near-black ground `primary` was 2.68:1 and `primary-container` was
15.19:1. On `muted` the order swaps, `primary` is 6.83:1 and 8.20:1 while `primary-container` is
1.20:1 and 1.50:1. Nothing about the earlier decision was wrong. Its premise moved.

### Option C: document the exception and change nothing. Rejected.

It leaves a 1.90:1 brand mark shipping, leaves the 2.68:1 active indicator shipping, and leaves the
region permanently outside every gate this repository has. It also leaves the trap armed: the next
agent who writes any token class inside that file gets a value that is correct in one theme and
wrong in the other, with nothing to tell them. The seed offered this option on the assumption that
nothing was broken. Something is.

## What the design loses, and what carries the signal instead

**The loss is real and it is the whole cost of this decision.** A dark rail is a common way to say
"you are in the admin tool, where what you do affects the entire clan". That signal is worth
keeping, and inverting the palette will no longer carry it.

Three reasons that trade is still right here:

1. **Colour was never allowed to be the only channel.** Spec § 5 `T-06`, at line 772, is
   "Colour is never the only channel", and its criterion is "Every state (selected, error,
   precision, role, deceased, stub) carries text or an icon in addition to colour. Verified by
   rendering the screen set in greyscale and confirming every state is still identifiable." A rail
   that says "you are in admin" only by being dark disappears in that greyscale reading.
2. **The text channel already exists and is under-used.** `BackofficeSidebar.tsx:45` renders the
   word "Backoffice" at `text-[10px] text-gray-400`. It is the smallest text in the file. Promoting
   it to the rail's primary label, at `text-foreground` and a real size, states in words what the
   inversion was stating in colour, and it survives 200% text scale and a colour-blind reader.
3. **The backoffice is role-gated on the server**, at `layout.tsx:27`
   (`await requireRole(['admin', 'super_admin'], locale)`). Nobody arrives here by accident.

**Glass is not the answer, and this rejects it explicitly.** Spec § 2.6 gives floating nav bars
`surface` at 80% opacity with `blur(20px) saturate(1.08)`. This rail is `fixed` and `<main>` is
`ml-60`, so no content ever passes underneath it. A backdrop blur with nothing behind it to blur is
decoration, and § 2.6 caps glass at "at most one persistent surface per screen", which should be
spent on something that earns it.

**The two 1px lines go, rather than moving to a token.** `border-gray-800` at `:32` and `:74`
separates the brand row and the footer from the nav. Measured 2026-08-22 it is `#1e2939` on
`#030712`, **1.37:1** in both themes. The Arbor Heritage no-line rule
(`.claude/rules/tailwind.md` § 5) forbids a 1px border for section separation outright, so the
answer is spacing, not a different line colour. A background sub-step inside the rail is available
in principle, `card` on `muted`, but it measures 1.10:1 in light and 1.08:1 in dark, which is not
worth a second surface.

## The one measurement that is uncomfortable, stated plainly

The step between the rail and the content is **1.04:1 in light** and **1.16:1 in dark** (`muted`
against `background`, measured 2026-08-22). The light figure is weak. It is weaker than the
decorative `border` token, which `contrast.test.ts:27-33` records at 1.13:1, and a 1.04:1 step on a
240px full-height rail will read as almost no boundary at all.

**The cause is not this decision. It is a known open value.** Web's light `muted` is `#f3f4f6`,
which is a cool Tailwind grey. Spec § 2.1's `surface-container` is `#EDE6D7`, a warm ground.
ADR-041 named the gap and deliberately left it open, at its own "What this ADR deliberately does not
decide": "**`muted #f3f4f6`**, a cool grey among warm grounds. Same reason." Measured 2026-08-22,
with the spec value the same step is **1.17:1**, and spec's `surface-container-high` `#E5DBC8` would
give **1.29:1**. Dark already holds the spec value, `#24221a`, which is why dark measures 1.16:1 and
light does not.

**This ADR does not move `muted`.** That token is composed by many screens, so changing it is its
own decision with its own blast radius, and taking it here would hide a palette change inside a
backoffice change. It is recorded as an open question below, and the rail is the screen that will
show the difference first.

## What has to change (not landed here)

One file each, and **the aside must be converted whole in one edit**. A partial conversion is worse
than either end state: measured 2026-08-22, `text-gray-100` on `muted` is **1.00:1** in light and
`text-gray-400` on `muted` is **2.36:1** in light, so any ink left behind becomes unreadable the
moment the ground moves. The palette sweep must not take this file one utility at a time.

`web/src/components/backoffice/BackofficeSidebar.tsx`

| Line | From | To |
|---|---|---|
| `:30` | `bg-gray-950 text-gray-100` | `bg-muted text-foreground` |
| `:32` | `border-b border-gray-800` | no border; separate with spacing |
| `:33-41` | the 2026-08-14 comment | replace with this ADR's numbers and a pointer here |
| `:42` | `text-primary-container` | `text-primary` |
| `:45` | `text-[10px] text-gray-400` | `text-xs text-foreground`, and promote it per "what carries the signal" |
| `:62` | `text-gray-400 hover:bg-gray-800 hover:text-gray-100` | `text-muted-foreground hover:bg-card hover:text-foreground` |
| `:74` | `border-t border-gray-800` | no border; separate with spacing |
| `:77` | `text-gray-400 hover:bg-gray-800 hover:text-gray-100` | same as `:62` |

`web/src/app/[locale]/backoffice/layout.tsx`

| Line | From | To |
|---|---|---|
| `:30` | `bg-gray-900` | `bg-background` |
| `:32` | `bg-gray-50` | `bg-background` |

**Verification for that seed.** The full web gate in `web/CLAUDE.md`. No new row in
`contrast.test.ts`, because every pair the converted rail composes is already in `CASES`; say that
in the seed rather than leaving the field empty. The rail sits behind a Supabase session and a
server-side role check, so `e2e/dark-theme.spec.ts` cannot reach it as that spec stands. Measure it
the way this ADR did, and say so: build, then render the real compiled stylesheet against the real
markup in Chromium under both emulated schemes, screenshot, and read the pixels back.

**One thing that seed must also do.** `.claude/rules/tailwind.md` § 3 currently ends with a
paragraph saying the aside "is still hand-built and is now the odd one out", and repeats the
2026-08-14 `primary-container` figures. Both stop being true when the seed lands. Rewrite that
paragraph in the same change.

## Two things found in the same file, recorded rather than taken

Both were read at source on 2026-08-22 and neither is a colour question, so neither is decided here.

- **The rail is half untranslated, and the half this ADR wants to promote is the untranslated
  half.** The four nav labels come from `t(labelKey)` at `BackofficeSidebar.tsx:66`, and
  `web/messages/vi.json` holds real copy for them: "Tổng quan", "Thành viên", "Dòng họ",
  "Cây gia phả". The brand row at `:44-45` renders the literal strings `FamilyRoots` and
  `Backoffice`, and the footer button at `:80` renders the literal string `Sign out`. `vi` is the
  default locale for this product. Promoting "Backoffice" to the rail's primary label, which is what
  "what carries the signal" asks for, puts an English word at the top of a Vietnamese rail. **The rebuild
  must add a `Backoffice.rail_label` message and use it**, or the design change it lands is worse
  than what it replaces. The `Sign out` string is the same defect one row down and is not this
  ADR's to fix.
- **`layout.tsx:30` may be unreachable.** `<main>` at `:32` is `min-h-screen flex-1`, so the
  `bg-gray-900` wrapper behind it did not appear anywhere in the rendered probe at 1280 by 800.
  Whether any viewport reveals it is unanswered.

## What was measured, and how

**Method, so that a later reader can repeat it rather than trust it.** The aside is behind a
Supabase session and a `requireRole` check, so no existing spec can reach it. Instead:
`pnpm build` was run on this branch, which emitted the real stylesheet to
`web/.next/static/chunks/07xe4inox9nl7.css`. A static page linking that stylesheet and carrying the
exact class strings from `BackofficeSidebar.tsx` and `layout.tsx` was rendered in Chromium
(Playwright 1.62.1, `deviceScaleFactor` 1) under `colorScheme: 'light'` and `colorScheme: 'dark'`.
Grounds were read as pixels from the screenshot, decoded through a canvas. Inks were read from
`getComputedStyle` and converted to sRGB by painting them into a canvas, because glyph edges are
antialiased and WCAG grades the specified ink, not the edge. Ratios use the WCAG 2.1
relative-luminance formula, the same one `contrast.test.ts:126-140` uses. All figures below are
**2026-08-22**.

**What the build actually emits.** Tailwind 4.3.3 declares `--color-gray-950` as
`oklch(13% 0.028 261.692)` (`node_modules/tailwindcss/theme.css:236`), and the build emits both an
sRGB fallback `#030712` and a wide-gamut `lab(1.90334% .278696 -5.48866)`. Chromium painted
`#030712`. So the `#030712` that this ADR and ADR-045 both quote is correct as rendered, even
though the source value is no longer a hex.

### The aside as it stands

| Pair | Light | Dark |
|---|---|---|
| aside ground `#030712` against content ground `#f9fafb` | 19.27:1 | 19.27:1 |
| brand mark `text-primary-container` on the aside | **15.19:1** `#d6e4ce` | **1.90:1** `#2b4526` |
| wordmark `text-gray-100` `#f3f4f6` on the aside | 18.30:1 | 18.30:1 |
| sub-label and idle nav `text-gray-400` `#99a1af` on the aside | 7.74:1 | 7.74:1 |
| active nav label `primary-foreground` on `primary` | 7.52:1 | 8.10:1 |
| active nav fill `primary` against the aside ground | **2.68:1** | 10.37:1 |
| `border-gray-800` `#1e2939` on the aside ground | 1.37:1 | 1.37:1 |

The 2.68:1 and 15.19:1 figures reproduce the seed's own numbers exactly. The 1.90:1 figure is the
one that did not exist when they were taken.

### Grounds that are not the content ground, for completeness

| Pair | Ratio |
|---|---|
| `#030712` against the light page `background` `#fbf8f1` | 18.98:1 |
| `#030712` against the dark page `background` `#15140f` | **1.09:1** |

The second row is the state the palette sweep creates if it tokenises `layout.tsx` before this decision
lands. It is why the two must be ordered.

### The chosen ground

| Pair | Light | Dark |
|---|---|---|
| `muted` against `background`, the rail-to-content step | **1.04:1** | **1.16:1** |
| `foreground` on `muted` | 15.81:1 | 13.41:1 |
| `muted-foreground` on `muted` | 5.17:1 | 6.07:1 |
| `primary` on `muted` | 6.83:1 | 8.20:1 |
| `primary-foreground` on `primary` | 7.52:1 | 8.10:1 |
| `input` on `muted` | 3.53:1 | 6.07:1 |
| `card` on `muted`, a possible sub-step, rejected | 1.10:1 | 1.08:1 |
| `primary-container` on `muted`, which is why the mark moves | 1.20:1 | 1.50:1 |
| `text-gray-100` left behind on `muted` | 1.00:1 | 14.47:1 |
| `text-gray-400` left behind on `muted` | 2.36:1 | 6.12:1 |

### If light `muted` ever takes its spec value

| Pair | Ratio |
|---|---|
| spec `surface-container` `#EDE6D7` against `background` `#fbf8f1` | 1.17:1 |
| spec `surface-container-high` `#E5DBC8` against `background` `#fbf8f1` | 1.29:1 |
| web's current `muted` `#f3f4f6` against `background` `#fbf8f1` | 1.04:1 |

## What this ADR deliberately does not decide

- **The value of `muted`.** ADR-041 left it open on purpose and this does not take it. It is the
  open question below.
- **A theme switch.** ADR-045 owns that, and nothing here revisits it.
- **The other 393 palette utilities.** The palette sweep, whose out-of-scope line names this aside.
  That line stays correct: the sweep must still leave `BackofficeSidebar.tsx` alone, and it must now also
  leave `layout.tsx:30` and `:32` to the seed that converts the rail, because the two files have to
  move together.
- **Whether an `inverse-surface` role should exist for some other purpose.** This says it is the
  wrong tool for a persistent rail. A transient snackbar or an undo toast is the case M3 names, and
  no such component exists in `web/src` today. If one is built, that is a new decision with a real
  subject.
- **The wordmark inside the rail at 320px and 200% text scale.**
  `.claude/rules/tailwind.md` § 7 records that it has never been measured. Still true, still a
  different question.
- **The `bg-gray-900` wrapper at `layout.tsx:30`.** This ADR points it at `bg-background`, but it was
  not visible in the rendered probe, so whether it is reachable at all is unanswered.

## Open question this creates

**Light `muted` is `#f3f4f6` and spec § 2.1's `surface-container` is `#EDE6D7`.** With the current
value the rail-to-content step is 1.04:1, which is weak enough to be worth calling a defect once
the rail is light. With the spec value it is 1.17:1. Deciding it needs one thing this ADR cannot
supply on its own: a reading of every screen that composes `bg-muted` today, because the token is
shared. That reading is the work, and it is not a backoffice question.

## Related

- **The four specimens, rendered**: <https://claude.ai/code/artifact/69ed64e3-d624-4dae-8840-dfd7700deebc>.
  It shows the rail as it stands and as decided, in both colour schemes, with every ratio on this
  page attached to the frame it came from. The 1.90:1 mark is visible there rather than described.
  It is a picture of the measurements, not a second source for them: this ADR is the source.
- [ADR-045](045-dark-mode-prefers-color-scheme-only.md), whose "What this decision does not buy you"
  handed this question here, and whose account of the vanishing boundary is corrected above.
- [ADR-041](041-primary-green-heritage-family-single-background.md) for the light palette, for the
  refusal to invent values that § 2.1 does not publish, and for the open `muted` value.
- [`../superpowers/specs/2026-08-02-design-system-and-screens.md`](../superpowers/specs/2026-08-02-design-system-and-screens.md)
  § 2 line 70 for the M3 naming rule, § 2.1 and § 2.2 for the role lists that publish no inverse
  surface, § 2.6 for glass and its cap, § 5 `T-06` for the one-channel rule.
- [`../../.claude/rules/tailwind.md`](../../.claude/rules/tailwind.md) § 3 for the paragraph that
  the rebuild must rewrite, § 5 for the no-line rule, § 7 for what `contrast.test.ts` cannot see.
- `web/src/app/contrast.test.ts`, whose `CASES` table already holds every pair the converted rail
  composes.
