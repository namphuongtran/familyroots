# Design System & Screen Specification — Arbor Heritage (web + mobile)

## Type
Design specification (product design; no application code)

## Date
2026-08-02

## Owner
Product design

## Consumers
- web (Next.js 16 / React 19 / Tailwind v4 `@theme`)
- mobile (Flutter / `ThemeExtension`)

## Status
Proposed. This document **extends** the Arbor Heritage mandates in `mobile/CLAUDE.md`
and the repo-root `CLAUDE.md`; it does not replace them. Where this document and
those mandates disagree, the mandates win and this document is the bug.

---

## 0. Scope and sources of truth

| Concern | Source of truth | This doc's job |
|---|---|---|
| Design mandates (no-line rule, faces, radii, glass, ambient depth, never `#000000`) | `mobile/CLAUDE.md` § Arbor Heritage | Obey and extend into a full token set |
| đời / đa thê / pedigree collapse / thủy tổ | `docs/architecture/tree-read-model.md` | Turn into rendering rules |
| Domain invariants, Vietnamese glossary | `docs/architecture/domain-rules.md` | Turn into form validation + copy |
| `HistoricalDate`, envelope, cursor pagination | `docs/contracts/README.md` | Turn into date/list presentation rules |
| Real client states (pending, suspended, unverified, multi-clan, `clan_founder_not_found`) | `docs/contracts/frontend-integration-guide.md` | Turn into screens, not error toasts |
| Role affordances | `docs/architecture/rbac.md` | Turn into per-role UI rules |

**Non-goals.** No component code, no route changes, no contract changes. Nothing here
asks the backend for a new endpoint; where the design wants one that does not exist, it
is filed in §9 as an open question and the design ships without it.

---

## 1. Who we design for — the constraints, restated as rules

The clan is the user, not a segment of the clan. A 19-year-old on a flagship and a
78-year-old trưởng họ on a five-year-old Android on weak 3G are both first-class. That
produces six hard rules that every screen in §7 is checked against:

1. **`vi` is the design locale.** Layouts are composed and reviewed in Vietnamese with
   full diacritics first. English is the translation, not the source. Vietnamese runs
   roughly 10–25% longer than English and its diacritic stacks are taller — nothing may
   be sized from an English string.
2. **Body text starts at 17px / 17sp.** Not 14, not 16. `body-lg` is the default, and
   `body-sm` (14) is never used for content a user must read to act.
3. **Every screen survives 200% OS text scale** at 320 dp width with no clipping and no
   overlap. Fixed heights on anything containing text are forbidden.
4. **Nothing depends on hover** and nothing depends on an image loading. Avatars are
   initials by default and photographs are an enhancement.
5. **Weak network is the normal case.** Shape-matched skeletons, reserved space (zero
   layout shift), explicit retry, and an honest offline state — never an infinite
   spinner.
6. **Contrast floor is WCAG AA and it is enforced at the token level** (§6), so a
   designer cannot accidentally ship an unreadable pairing.

---

## 2. Design tokens

Tokens are expressed as **semantic roles**, never as raw colour names. A component
never references "green" or "red"; it references `primary` or `danger`. This is what
lets the same component tree render both themes and a future high-contrast mode.

Naming follows Material 3 role naming, because `mobile/CLAUDE.md` already speaks it
(`on_surface`, `surface-container-low`, `outline_variant`). Web uses the same names in
kebab-case; Flutter uses the same names in lowerCamelCase.

### 2.1 Colour — light theme (default)

**Surfaces.** The no-line rule means boundaries are *background steps*, so we need more
surface levels than a bordered system would.

| Token | Value | Use |
|---|---|---|
| `surface` | `#FBF8F1` | Page ground (warm paper) |
| `surface-container-lowest` | `#FFFDF9` | Cards that must lift off the page |
| `surface-container-low` | `#F4EFE4` | Default card / field fill |
| `surface-container` | `#EDE6D7` | Grouped rows, list section grounds |
| `surface-container-high` | `#E5DBC8` | Hovered/pressed container, selected row |
| `surface-container-highest` | `#DCD1BA` | Pressed state, scrubber tracks |
| `on-surface` | `#1D1B16` | Primary text (**mandated**; never `#000000`) |
| `on-surface-variant` | `#57503F` | Secondary text, icons |
| `on-surface-muted` | `#6E6653` | Tertiary text, timestamps, helper text |
| `outline-variant` | `#B3A98F` | **Only** in high-contrast mode, at 15% opacity |
| `scrim` | `rgba(29,27,22,0.44)` | Behind dialogs/sheets |

**Interactive — leaf (the arbor).**

| Token | Value | Use |
|---|---|---|
| `primary` | `#3E5C38` | Primary actions, active nav, links |
| `on-primary` | `#FFFFFF` | Text/icon on `primary` |
| `primary-container` | `#D6E4CE` | Tonal buttons, selected chips |
| `on-primary-container` | `#14260F` | Text on `primary-container` |
| `secondary` | `#7A6248` | Secondary actions, bark accents |
| `secondary-container` | `#EADDCB` | Quiet tonal surfaces |
| `on-secondary-container` | `#2A2013` | Text on `secondary-container` |

**Ceremonial — lacquer & gilt.** Reserved. See §9-J1 for why this is a separate family
from `primary`.

| Token | Value | Use |
|---|---|---|
| `heritage` | `#A3182F` | Thủy tổ marker, giỗ (death anniversary), ancestral emphasis |
| `on-heritage` | `#FFFFFF` | Text on `heritage` |
| `heritage-container` | `#F6DFE0` | Giỗ chips, thủy tổ card ground |
| `on-heritage-container` | `#4A0A14` | Text on `heritage-container` |
| `gilt` | `#8A6A16` | Gold **text/icons** (contrast-safe) |
| `gilt-decor` | `#D4AF37` | Gold **fills, strokes, rules only** — never text |

**Semantic status.** Separate from both accent families; status is never carried by the
brand hue.

| Token | Value | Container | On-container |
|---|---|---|---|
| `success` | `#2E6A4E` | `#D5E9DC` | `#0C2A1B` |
| `warning` | `#8A5A00` | `#F8E6C6` | `#3A2400` |
| `danger` | `#A32218` | `#F8DED9` | `#410B06` |
| `info` | `#2A5A78` | `#D8E7F0` | `#0A2433` |

**Focus.** `focus-ring: #1D1B16` (light) / `#F1EBDE` (dark) — the on-surface colour, at
3px with a 2px `surface`-coloured offset. Using on-surface rather than an accent
guarantees ≥3:1 against every ground in the system, including `primary` and `heritage`
fills.

### 2.2 Colour — dark theme

Not an inversion. Ground is warm ink, never `#000000`; the leaf lifts, the lacquer
desaturates so it does not vibrate on dark.

| Token | Value | | Token | Value |
|---|---|---|---|---|
| `surface` | `#15140F` | | `primary` | `#A3C398` |
| `surface-container-lowest` | `#100F0B` | | `on-primary` | `#12280D` |
| `surface-container-low` | `#1D1B15` | | `primary-container` | `#2B4526` |
| `surface-container` | `#24221A` | | `on-primary-container` | `#CBE3C2` |
| `surface-container-high` | `#2D2A20` | | `secondary` | `#D3BC9E` |
| `surface-container-highest` | `#383426` | | `secondary-container` | `#4A3A27` |
| `on-surface` | `#F1EBDE` | | `heritage` | `#F0A0A8` |
| `on-surface-variant` | `#C6BDA8` | | `heritage-container` | `#4E1520` |
| `on-surface-muted` | `#A99F89` | | `on-heritage-container` | `#FFD9DC` |
| `outline-variant` | `#6E6653` | | `gilt` | `#E3C464` |
| `scrim` | `rgba(8,7,5,0.62)` | | `gilt-decor` | `#D4AF37` |

Status on dark: `success #8FCFAA` / `#1B3A2A`, `warning #E8B563` / `#3E2A06`,
`danger #F0A79C` / `#4A1811`, `info #9CC8E4` / `#12303F`.

Shadow colour on dark is `rgba(8,7,5,0.55)` — a near-ink, not pure black.

### 2.3 Type scale

Faces are mandated: **Plus Jakarta Sans** (headings, display, person names, branch
titles, milestones) and **Manrope** (body, labels, data). No system-font fallback.

| Token | Face | Size | Line height | Weight | Tracking | Use |
|---|---|---|---|---|---|---|
| `display-lg` | Jakarta | 40 | 48 (1.20) | 800 | −0.02em | Screen hero on desktop only |
| `display-md` | Jakarta | 32 | 40 (1.25) | 700 | −0.015em | Page title |
| `headline` | Jakarta | 26 | 34 (1.31) | 700 | −0.01em | Section head, person name on profile |
| `title-lg` | Jakarta | 21 | 30 (1.43) | 600 | 0 | Card title, person name in tree node |
| `title-md` | Jakarta | 18 | 26 (1.44) | 600 | 0 | List row name, dialog title |
| `body-lg` | Manrope | 17 | 28 (1.65) | 400 | 0 | **Default body** |
| `body-md` | Manrope | 15 | 24 (1.60) | 400 | 0 | Dense metadata, table cells |
| `body-sm` | Manrope | 14 | 22 (1.57) | 400 | 0 | Captions only — never load-bearing |
| `label-lg` | Manrope | 16 | 22 (1.38) | 600 | +0.005em | Button text |
| `label-md` | Manrope | 14 | 20 (1.43) | 600 | +0.01em | Chips, badges, field labels |
| `overline` | Manrope | 12 | 16 (1.33) | 700 | +0.08em | Eyebrow labels — see caps rule below |
| `numeric` | Manrope | inherit | inherit | inherit | 0 | `font-variant-numeric: tabular-nums` |

**Vietnamese typography rules (binding):**

- Minimum line-height ratio is **1.20 for display, 1.30 for titles, 1.55 for body**.
  Vietnamese stacks two marks (`ế`, `ộ`, `ữ`) and a tighter leading collides them with
  the descenders of the line above.
- **`overline` may only be set in caps for words with no tone marks.** `THÀNH VIÊN`
  loses its diacritics to optical crowding at 12px; use sentence case (`Thành viên`)
  with the same tracking instead. Caps is available for `ĐỜI`, `GIỖ`, short ASCII.
- Never `text-transform: uppercase` on user data (names, place names, biographies).
- Person names are always Jakarta, never Manrope, at every size — a name is a heading
  wherever it appears.
- `tabular-nums` on every column of years, đời numbers, counts, and dates.

### 2.4 Spacing

4px base, geometric-ish ramp. Both clients use the same numbers (px on web, logical px
in Flutter).

`space-1` 4 · `space-2` 8 · `space-3` 12 · `space-4` 16 · `space-5` 20 · `space-6` 24 ·
`space-8` 32 · `space-10` 40 · `space-12` 48 · `space-16` 64 · `space-20` 80 ·
`space-24` 96

Applied defaults: screen gutter `space-5` (mobile) / `space-8` (desktop); card padding
`space-5`; gap between stacked cards `space-4`; section gap `space-10`; gap between two
adjacent tap targets ≥ `space-2`.

**Layout, not margins.** Sibling groups are laid out with flex/grid `gap`, never with
per-child margins — margins collapse and double under 200% text scale and produce the
uneven rhythm this system is trying to avoid.

### 2.5 Radii

Mandated: `9999px` for primary buttons, `2rem` for nodes, never `sm`/`none`.

`radius-xs` 8 (chips, badges) · `radius-sm` 12 (inputs, small cards) ·
`radius-md` 16 (cards) · `radius-lg` 20 (panels) · `radius-xl` 28 (dialogs, sheets —
top corners only for bottom sheets) · `radius-node` 32 (tree nodes, person cards) ·
`radius-pill` 9999 (buttons, chips-as-buttons, avatars)

**Floor: 8.** Nothing in the system is squarer than `radius-xs`. Full-bleed images
inside a card inherit the card's inner radius (`radius − padding`), never square off.

### 2.6 Elevation and glass

Ambient depth only — no rigid drop shadows, no hard offsets.

| Token | Light | Use |
|---|---|---|
| `elev-0` | none | Flat content on `surface` |
| `elev-1` | `0 1px 2px rgba(29,27,22,.03), 0 8px 24px rgba(29,27,22,.04)` | Resting card |
| `elev-2` | `0 2px 4px rgba(29,27,22,.03), 0 16px 32px rgba(29,27,22,.06)` | Hover/raised (the mandate's 32px @ 6%) |
| `elev-3` | `0 4px 8px rgba(29,27,22,.04), 0 32px 64px rgba(29,27,22,.10)` | Dialog, bottom sheet, dragged node |

**Glass** (floating nav bars, the tree's floating toolbar, the mobile bottom bar):
background = `surface` at **80% opacity**, `backdrop-filter: blur(20px) saturate(1.08)`.
Flutter equivalent is `BackdropFilter(ImageFilter.blur(sigmaX: 10, sigmaY: 10))` —
CSS blur radius ≈ 2 × Gaussian sigma, so 20px CSS = sigma 10.

**Glass fallback is mandatory.** On devices without backdrop-filter support, and
whenever the device reports reduced transparency or low power, glass degrades to an
opaque `surface-container-low`. A five-year-old Android must not pay a per-frame blur
for a scrolling list. Rule: glass is used on **at most one persistent surface per
screen**.

### 2.7 Motion

| Token | Duration | Use |
|---|---|---|
| `dur-1` | 90ms | Press/release, checkbox, chip toggle |
| `dur-2` | 160ms | Hover, focus ring, small fades |
| `dur-3` | 240ms | Card enter/exit, tab change, expand |
| `dur-4` | 380ms | Dialog, bottom sheet, route transition |
| `dur-5` | 600ms | Tree pan/zoom-to-node, ambient |

Easing: `ease-standard cubic-bezier(.2,0,0,1)` · `ease-decelerate cubic-bezier(.05,.7,.1,1)`
(entering) · `ease-accelerate cubic-bezier(.3,0,.8,.15)` (exiting).

**Reduced motion** (`prefers-reduced-motion` / `MediaQuery.disableAnimations`): all
transforms become instant; opacity transitions are capped at 90ms; the tree never
auto-pans, it jumps; skeleton shimmer becomes a static tint.

### 2.8 Expressing tokens in both clients

The token set is deliberately flat name→value so it maps 1:1 onto both platforms.
These are spec illustrations, not code to copy into the app.

Web — Tailwind v4 `@theme`:

```
@theme {
  --color-surface: #FBF8F1;
  --color-surface-container-low: #F4EFE4;
  --color-on-surface: #1D1B16;
  --color-primary: #3E5C38;
  --color-heritage: #A3182F;
  --text-body-lg: 17px;
  --text-body-lg--line-height: 28px;
  --spacing-5: 20px;
  --radius-node: 32px;
  --shadow-elev-2: 0 2px 4px rgb(29 27 22 / .03), 0 16px 32px rgb(29 27 22 / .06);
}
```

Dark theme redefines only the `--color-*` group under
`@media (prefers-color-scheme: dark)` **and** `:root[data-theme="dark"]`; components
never branch on theme themselves.

Flutter — one `ThemeExtension` per token family (`ArborColors`, `ArborType`,
`ArborSpace`, `ArborShape`, `ArborElevation`, `ArborMotion`), each with `copyWith` and
`lerp`, registered on both `ThemeData.light()` and `.dark()`. Widgets read
`Theme.of(context).extension<ArborColors>()!.heritage` — never a `const Color` literal.
`ColorScheme` is populated from the same values so Material widgets inherit correctly.

### 2.8.1 What the web app actually has today — measured, 2026-08-03

`web/src/app/globals.css` already carries a Tailwind v4 `@theme` block, written before
this document existed. It was never reconciled against §2, and it is not a naming
mismatch: **the two disagree about what the primary colour is, and most of what the file
declares does not reach the browser.**

Everything below was measured, not read — a dev server on `127.0.0.1:3210`, Chromium via
Playwright, `getComputedStyle` on a probe element, and WCAG ratios computed from the hex
values in the file. Reproduce with `pnpm dev` and the probe described at the end.

**A. Every semantic colour token is dead.** `@theme` defines thirteen of them as
`hsl(var(--x))` — `background`, `foreground`, `border`, `input`, `ring`, `secondary`,
`secondary-foreground`, `destructive`, `muted`, `muted-foreground`, `accent`, `popover`,
`card` — while `:root` defines those variables as **hex strings** (`--background: #f8f4ec`).
`hsl()` takes hue/saturation/lightness, so `hsl(#f8f4ec)` is invalid and the declaration is
dropped. This is the shadcn convention applied with the wrong value format: shadcn stores
bare channels (`45 33% 95%`), not hex.

Proof that they are dropped rather than merely wrong: probed in the browser, all thirteen
resolve to the *same* computed value — the inherited body colour — including
`secondary`, whose `--secondary` is **never defined anywhere in the file**. If `hsl(#hex)`
were being parsed, `border` (`#e5e7eb`) and `destructive` (`#ef4444`) could not agree.

So `bg-background`, `text-foreground`, `border-border`, `bg-card`, `bg-muted`,
`text-muted-foreground`, `text-destructive`, `bg-popover`, `bg-accent` and `ring-ring` all
do nothing today. Anything that looks correct on screen looks correct by inheritance.

**B. There is no dark theme.** `@custom-variant dark (&:is(.dark *))` is declared, and no
`.dark` block exists anywhere in the stylesheet — confirmed by walking every loaded
`CSSRule`. Every `dark:` utility in the codebase resolves against light values. §2.2 of
this document specifies a full dark palette; none of it is implemented, and because of (A)
there is no working light palette to invert either.

**C. The one font that loads is never used, and both fonts are the wrong fonts.**
`src/app/[locale]/layout.tsx` loads `Inter` through `next/font/google` with the Vietnamese
subset and exposes it as `--font-inter`. Nothing references `--font-inter`. `globals.css`
instead hardcodes `body { font-family: 'Inter', 'Noto Sans', sans-serif }` — a literal
family name, which is *not* the obfuscated name `next/font` generates. Measured body font:
`Inter, "Noto Sans", sans-serif`, resolved from the hardcoded rule. So the correctly
subsetted Vietnamese Inter is downloaded and discarded, and the text renders in whatever
the device happens to have — precisely the silent-fallback failure the Arbor Heritage
mandate forbids, on precisely the device (§1) we designed for.

`Playfair Display` is named for headings and is **never loaded at all** — no `next/font`
call, no `@font-face`, no dependency. Every heading falls back to Noto Serif or Georgia.

And neither is the specified typeface. The mandate is **Plus Jakarta Sans** for headings
and **Manrope** for body. Neither string appears anywhere in the repository.

The font class is also applied to a `<div>` in the `[locale]` layout, the same structural
defect as R-lang — see §9.

**D. Three names for "primary", and the app's primary is not this document's primary.**
`--color-primary-500`, a bare `--color-primary`, and `:root --primary` all hold `#c41e3a`.
The third is consumed by nothing: unlike the other semantics, `--color-primary` is a
literal, not an `hsl(var(--primary))` indirection, so `:root --primary` and
`--primary-foreground` are dead code. **Use `--color-primary`**; it is the one that
generates `bg-primary`.

The deeper conflict: `#c41e3a` is a red, and §2.1 of this document makes primary a green
(`#3E5C38`) with red reserved as `--color-heritage` (`#A3182F`). The app's "primary" is
therefore this document's *accent*, and this document's actual primary does not exist in
the app. **This document is correct and the app is the bug** — §2.1's rationale is that a
red-dominant UI reads as alarm in a product whose most common actions are neutral, and red
must stay affordable for `heritage` moments and destructive confirmation. Renaming is a
sub-project B implementation task, and it is not cosmetic: `bg-primary` currently paints
things red across the app.

**E. Two different backgrounds are both called the background.** Measured body background
is `#fdfbf7` (`--color-cream`), while `--background` says `#f8f4ec` and `--cream` in
`:root` says `#f8f4ec` too. Three names, two values, and the body uses the one the
semantic token disagrees with. `--color-cream-50` is also `#fdfbf7` and `--color-cream-100`
is `#f8f4ec`, so both values exist in the ramp under different indices.

**F. Contrast — computed, not assumed.** Ratios against the hex values actually in the file:

| Pair | Ratio | Verdict |
|---|---|---|
| `foreground #1a1a1a` on `background #f8f4ec` | 15.87 | passes |
| `primary-700 #8b0000` on white | 10.01 | passes |
| `accent-foreground #92400e` on `accent #fef3c7` | 6.37 | passes |
| `primary #c41e3a` on white | 5.84 | passes |
| `muted-foreground #6b7280` on `card #ffffff` | 4.83 | passes |
| **`muted-foreground #6b7280` on `background #f8f4ec`** | **4.41** | **fails AA normal text** |
| **`destructive-foreground #ffffff` on `destructive #ef4444`** | **3.76** | **fails AA normal text** |
| **`destructive #ef4444` on white** | **3.76** | **fails AA normal text** |
| **`gold-500 #d4af37` on white** | **2.10** | **fails everything for text** |
| **`gold-500 #d4af37` on `cream #fdfbf7`** | **2.03** | **fails everything for text** |
| `border #e5e7eb` on `background #f8f4ec` | 1.13 | below 3:1 for non-text |

Four real failures, and note the shape of the first: `muted-foreground` **passes on cards
and fails on the page background**. Secondary text is exactly what that token is for, so
the same helper text is compliant inside a card and non-compliant beside it. A reviewer
checking one screen would call it fine.

`destructive` failing matters more than it looks: 3.76 means both red error text *and* the
white label on a red confirm button are non-compliant, so the destructive path — the one
place a 78-year-old trưởng họ most needs to read what is about to happen — is the least
legible thing in the palette. Darken it; `#b91c1c` and below clears 4.5.

`gold` is unusable for text at any size and must be restricted to non-text ornament. That
is consistent with §2.1 treating gold as ornament, but nothing in the app enforces it and
`text-gold-500` is a class someone will reach for.

`border` at 1.13 is *not* a defect by itself — the Arbor Heritage mandate says not to use
1px borders for section separation and to express boundaries with background shifts. The
token exists mainly for inputs, where a 3:1 boundary is required. It needs a darker value
for that use, or inputs need a filled treatment instead.

**Nothing here is fixable in this document.** Every item is application code. The order
that matters, for whoever implements it: (A) first, because until the semantic tokens
resolve, nothing else can be verified on screen; then (C), because a fallback font changes
every measurement in §2.3 and §6; then (F); then (D) and (E) together as one renaming.
(B) last — a dark palette built on a broken light one cannot be checked.

**How this was measured**, so it can be re-run after a fix: start the dev server, then in
Chromium set `color: hsl(var(--<name>))` on a probe element and read
`getComputedStyle`. All thirteen returning one identical value — and matching the
inherited body colour — is the signature of the invalid-declaration failure. When the
tokens are fixed, they must return thirteen *different* values.

---

## 3. Domain presentation primitives

These are the rules that make this a gia phả and not a CRUD app. They are shared
behaviour, specified once, implemented in both clients.

### 3.1 `HistoricalDate` — the five precisions

Every genealogical date arrives as `{date, precision, display, lunar}`. There is exactly
one renderer, `<HistoricalDate>` / `ArborDate`, and no screen formats a date itself.

| `precision` | Renders | Precision affordance | Example |
|---|---|---|---|
| `exact` | `date` formatted `dd/MM/yyyy` | none | `15/08/1948` |
| `year` | `display`, falling back to the year of `date` | chip `năm` | `1948` + `năm` |
| `month` | `display`, falling back to `MM/yyyy` | chip `tháng` | `08/1948` + `tháng` |
| `circa` | `display`, falling back to `khoảng {year}` | chip `khoảng` | `khoảng 1750` + `khoảng` |
| `unknown` | `Không rõ` | chip `không rõ` | `Không rõ` |

Rules:

- **Never invent precision.** If `precision != "exact"`, the exact `date` value is never
  shown to the user, even though the API sends one (it exists for sorting and
  anniversaries only).
- **The precision chip is text, not colour.** `label-md`, `on-surface-variant` on
  `surface-container`, `radius-xs`. Estimated dates are not warnings — a 300-year-old
  record being approximate is normal and must not look like an error.
- **Lunar is a second line, never inline.** When `lunar` is non-null it renders below
  the solar line as `Âm lịch · 15/08 Nhâm Tý` in `body-md` / `on-surface-muted`. It is
  never merged into the solar string and never parsed.
- **`lunar` is user-entered text and is returned verbatim in every locale.** It is not
  translated, not reformatted, not validated against a calendar. See §9-J7.
- **Unknown is a first-class value, not an empty state.** A person with
  `precision: "unknown"` on both dates is a complete, valid record. The profile shows
  `Không rõ`, not a blank or a dash.
- Screen readers announce the rendered string plus, when present, `âm lịch, …`.

### 3.2 đời (generation) badge

`generation` comes from one backend authority (`con theo đời cha`) and **can legitimately
be `null`**.

- Present: `Đời {n}` — `label-md`, `on-heritage-container` on `heritage-container`,
  `radius-pill`, `tabular-nums`. đời is lineage, so it wears the ceremonial family.
- Null: **`Đời ?`** — `on-surface-variant` on `surface-container-high`, same shape. Never
  omitted, never guessed, never rendered as `Đời 0` or `Đời —`.
- `Đời ?` is tappable/focusable and opens a one-paragraph explainer:
  *"Chưa xác định được đời vì người này chưa nối được với thủy tổ của dòng họ. Khi quan
  hệ cha/mẹ được bổ sung, hệ thống sẽ tự tính lại."* Admins additionally get
  `Nối vào cây` → the relationship editor.
- Screen reader: `đời thứ 5` / `chưa xác định đời`.
- Sorting: null-đời **never** sorts as 0 or ∞ into the numeric run. Lists group them
  under an explicit `Chưa xác định đời` section at the end.

### 3.3 đa thê — grouping children by wife

A father's children are grouped under each wife via `mother_id` and
`mother_spouse_order`.

- Each group has a **WifeGroupHeader**: the wife's name in `title-md` (Jakarta) plus an
  order chip from `mother_spouse_order`: `1 → Vợ cả`, `2 → Vợ hai`, `3 → Vợ ba`,
  `n → Vợ thứ {n}`.
- `mother_spouse_order == null` but `mother_id` present → header shows the wife's name
  with no order chip. Order is a fact from the marriage record; absence of it is not
  "first".
- `mother_id == null` → the child appears in a final ungrouped section headed
  `Chưa rõ mẹ`. Not "Khác", not silently folded into the first wife.
- Groups are ordered by `spouse_order` ascending, `null` last, then `Chưa rõ mẹ`.
- The group header is **background-shifted, never ruled**: children of one wife sit on
  `surface-container-low` inset from `surface`, with `space-4` between groups. This is
  exactly the case the no-1px-border rule exists for.
- One wife's children are never visually subordinate to another's. Same node size, same
  type, same treatment; only the header differs.

### 3.4 Pedigree collapse stubs

A node with `pedigree_collapse_ref: true` displays but does not descend. Its
`children`/`spouses` are forced empty, and its `has_more_descendants` may still be
`true` — so the two fields disagree by design.

- Render the **full node** (same size, same name, same đời badge) plus a chip:
  `Nhánh chính ở nơi khác`.
- Replace the expand chevron with `Xem ở nhánh chính →`, which navigates to the
  canonical occurrence. **Never render an expand affordance on a stub**, regardless of
  `has_more_descendants` — an expander that yields nothing is the worst possible
  outcome on a weak network.
- Never grey a stub. Grey means deleted or inactive; this person is neither.
- Screen reader appends: `xuất hiện ở nhiều nhánh; nhánh chính ở nơi khác`.

### 3.5 Role → affordance

Three clan roles. The rule is **remove, do not disable**.

| Surface | admin | editor | viewer |
|---|---|---|---|
| Person profile header | `Sửa`, `Xóa`, `⋯` | `Sửa` | **`Đề nghị sửa`** (§7.9a) |
| Member list | `+ Thêm thành viên` FAB | `+ Thêm thành viên` FAB | *(no FAB)* |
| Tree node long-press sheet | Xem · Sửa · Thêm con · Thêm vợ/chồng · Đặt thủy tổ | Xem · Sửa · Thêm con · Thêm vợ/chồng | Xem hồ sơ · Tìm quan hệ · **Đề nghị sửa** |
| `clan_founder_not_found` | `Chọn thủy tổ` CTA | read-only explainer | read-only explainer |
| Events | tạo/sửa/xóa | tạo/sửa/xóa | *(no buttons)* |
| Documents | tải lên, xóa | tải lên | *(no buttons)* |
| Change-request queue (`Đề nghị sửa`) | full clan queue, duyệt/từ chối | full clan queue, duyệt/từ chối | **own proposals only, read-only** |
| Admin nav item | visible | hidden | hidden |

A viewer sees **zero disabled controls**. A screen full of greyed buttons reads as
"broken" to a non-technical user and as "you are not trusted" to a family member.
A viewer now has a real contribution path (`POST /change-requests`, ADR-037), so the
profile header carries a working action plus one quiet, permanent line in `body-md` /
`on-surface-muted`:

> Bạn đang xem gia phả với quyền **Người xem**. Bạn có thể gửi đề nghị sửa để quản trị
> hoặc biên tập viên xem xét.

Everything else a viewer cannot do is still absent rather than greyed. See §7.9 for the
full flow and §9-J5 for how the old "no endpoint" gap was closed.

### 3.6 Error code → UI state

Global rule: **switch on `error.code`, display `error.message`** (the backend localises
it). Codes below get a designed state; anything else falls through to the generic
`ErrorState`.

| Code | HTTP | UI |
|---|---|---|
| `email_not_verified` | 403 | Full screen: xác thực email + resend (§7.1c) |
| `account_deactivated` | 403 | Full screen block, sign out |
| `clan_suspended` | 403 | Full screen block + clan switcher if other clans (§7.2c) |
| `no_approved_clan_membership` | 403 | Route to pending or onboarding (§7.2a) |
| `multiple_clans_no_selection` | 400 | Clan picker (§7.2b) |
| `clan_founder_not_found` | 404 | **Onboarding state on the tree screen** (§7.4b) — never an error screen |
| `stale_write` | 409 | Conflict dialog (§7.7c) |
| `invalid_cursor` | 400 | Silent: drop cursor, refetch page 1, keep scroll |
| `rate_limited` | 429 | Inline countdown from `detail.retry_after`; disable submit |
| `auth_provider_unavailable`, `storage_unavailable` | 503 | Transient banner + retry — **never** "sai mật khẩu" |
| `relationship.parent_too_young` | 422 | Inline field error on the parent field |
| `change_request.target_conflict` | 409 | Reviewer conflict state (§7.9e) — **not** the same UI as `stale_write` |
| `change_request.target_deleted` | 409 | Reviewer blocked state (§7.9e), offering restore or reject |
| `change_request.not_pending` | 409 | "Đề nghị này đã được xử lý" + reload detail |
| `change_request.field_not_submittable` | 422 | Should be unreachable — the proposal form omits those fields. If seen, inline error naming `detail.fields` |
| `change_request.no_changes` | 422 | Should be unreachable — submit stays disabled until a field differs |
| `change_request_not_found` | 404 | Plain "Không tìm thấy đề nghị này." Never "bạn không có quyền" — the queue is not an enumeration oracle |
| `meta.warning` on a 2xx | — | Non-blocking toast after success, never a blocker |

**Two staleness codes, two different screens.** `stale_write` (§7.7c) is *my* edit
racing someone else's, resolved field-by-field by the person who was typing.
`change_request.target_conflict` (§7.9e) is *someone else's week-old proposal* no longer
applying, resolved by a reviewer who was not typing anything. They must never share a
dialog: the first asks "which of your two versions?", the second asks "is this proposal
still right?".

---

## 4. Component inventory

Every component below is specified for **default · hover · pressed · focus · disabled ·
loading · empty · error**, with the understanding that not every state applies to every
component (a button has no empty state; a list has no pressed state). "—" means the
state does not exist for that component and must not be invented.

### 4.1 Actions

**Button** — variants `primary` (filled `primary`), `tonal` (`primary-container`),
`ghost` (transparent, `primary` text), `danger` (filled `danger`), `heritage` (filled
`heritage`, reserved for ceremonial actions like `Đặt làm thủy tổ`). Sizes: `lg` 56dp,
`md` 48dp, `sm` 40dp (web pointer only). Always `radius-pill`, `label-lg`, horizontal
padding `space-6`.

| State | Treatment |
|---|---|
| default | Fill per variant, `elev-0` |
| hover (web) | Fill darkened 6% (light) / lightened 8% (dark), `elev-1`, `dur-2` |
| pressed | Fill darkened 12%, scale 0.98, `dur-1` |
| focus | 3px `focus-ring` + 2px offset, retained on `:focus-visible` and always on keyboard |
| disabled | `on-surface` @ 12% fill, `on-surface` @ 38% label, no shadow, `cursor: not-allowed`. **Reserve for transient states only** (form invalid, submitting) — never for permission (§3.5) |
| loading | Label stays in place, opacity 0.6; 20dp indeterminate ring replaces the leading icon slot; width does not change; `aria-busy`, `aria-live="polite"` announces `Đang lưu…` |

**IconButton** — 48dp mobile / 44px web, `radius-pill`, icon 24dp. Always has an
accessible name. Never the only carrier of a destructive action.

**FAB (mobile)** — 64dp, `primary`, `radius-pill`, `elev-2`, bottom-right above the
glass nav bar, respects safe area. Extends to a labelled pill (`+ Thêm thành viên`) on
first paint of an empty list, collapses to icon on scroll.

### 4.2 Inputs

**TextField** — filled: `surface-container-low`, `radius-sm`, min-height 56dp, label
**above** the field in `label-md` (not floating — floating labels shrink to ~11px and
Vietnamese diacritics disappear), helper text below in `body-md`.

| State | Treatment |
|---|---|
| default | `surface-container-low` fill, `on-surface` text, placeholder `on-surface-muted` |
| hover (web) | fill → `surface-container` |
| focus | 3px `focus-ring`, fill → `surface-container-lowest` |
| disabled | fill `on-surface` @ 6%, text @ 38%, label unchanged |
| read-only | fill `surface-container`, no ring, value selectable |
| error | fill `danger-container`, message below in `on-danger-container` **with an alert icon**, `aria-describedby`, `aria-invalid` |
| loading (async validate) | 20dp ring in the suffix slot; field stays editable |

No underline, no 1px outline, in any state. The focus ring is an accessibility
affordance and is explicitly exempt from the no-line rule (§9-J2).

**HistoricalDateField** — the composite that makes this product possible. Layout, top to
bottom:

1. Label (`Ngày sinh`).
2. Precision **SegmentedControl**: `Chính xác · Tháng · Năm · Khoảng · Không rõ`. Wraps
   to two rows under 200% text scale; never scrolls horizontally.
3. Conditional value area:
   - `Chính xác` → three `tabular-nums` fields `Ngày / Tháng / Năm` (not a calendar
     popover — a 1780 date is 240 taps away in a month picker), plus an optional native
     picker button for recent dates.
   - `Tháng` → `Tháng / Năm`. `Năm` → `Năm`. `Khoảng` → `Năm` + free-text `Cách ghi`
     prefilled `khoảng {năm}`. `Không rõ` → value area collapses entirely.
4. Optional `Ngày âm lịch (ghi trong gia phả)` free-text field, always available,
   helper: *"Ghi đúng như trong gia phả, ví dụ: 15/08 Nhâm Tý. Hệ thống không tự quy
   đổi."*
5. Live preview line showing exactly what the profile will display.

**Select**, **Checkbox** (24dp box / 48dp target), **Radio**, **Switch** (52×32 track) —
standard states; all carry a text label, never icon-only.

**SearchField** — `radius-pill`, leading search icon, trailing clear (appears only when
non-empty), 300ms debounce, `role="searchbox"`, results count announced politely.
Loading = 20dp ring replacing the clear button; the previous result list stays visible
and dims to 0.6 rather than being replaced by skeletons (avoids the flash-of-empty on
every keystroke over 3G).

### 4.3 Display

**Chip** — `label-md`, `radius-pill`, height 32 (display) / 40 (interactive). Kinds:
`neutral` (`surface-container` / `on-surface-variant`), `generation`
(`heritage-container`), `role`, `precision`, `status`, `filter` (selected =
`primary-container` + check icon — selection is never colour-only).

**Avatar** — `radius-pill`. **Initials are the default rendering**, not the fallback:
first letter of the last given name, `title-md` Jakarta on a tint deterministically
derived from the person id (six approved tints from the `secondary`/`primary` families,
all ≥4.5:1 against `on-surface`). A photo overlays it only after it loads. On image
error the initials are already there — no layout shift, no broken-image icon. Sizes 32 /
40 / 56 / 96. `alt` = the person's full name; when initials-only, the visual is
`aria-hidden` and the name is read from the adjacent text.

**PersonNodeCard** (tree) — `radius-node` (32), `surface-container-low`, `elev-1`,
padding `space-4`, min-width 200 / max-width 280. Contents: avatar 40, name
`title-lg` Jakarta (two lines max, ellipsis with full name in the sheet), đời badge,
life line (`1892 – khoảng 1961`) in `body-md` `tabular-nums`, and at most one status
chip. Thủy tổ nodes get a `heritage-container` ground plus a `Thủy tổ` chip in
`heritage`. Deceased is indicated by the death date's presence, not by greying.

States: default · hover `elev-2` + `surface-container` (web) · pressed scale 0.99 ·
focus 3px ring · selected `primary-container` ground + 3px `primary` ring · loading
skeleton of the identical shape · error (node failed to load) shows the id and a retry.

**ListRow / PersonRow** — min-height 72dp, avatar 40, name `title-md`, secondary line
`body-md` `on-surface-variant`, trailing đời badge. Rows are separated by **background
alternation is forbidden** (zebra striping is a rule by another name); separation comes
from `space-2` gaps and each row sitting on `surface-container-low` over `surface`.

**Banner** — inline, `radius-md`, tonal container per kind (`info`, `warning`, `danger`,
`success`, `heritage` for onboarding), leading icon, `body-lg` message, optional action
as a `ghost` button. Dismissible banners persist their dismissal per user per clan.

**EmptyState** — no illustration (an image that may not load cannot carry the message).
Typographic: `headline` line, `body-lg` explanation of *why* it is empty and *what
happens next*, one primary action if the role allows one, otherwise nothing. Never
"Không có dữ liệu".

**ErrorState** — `headline` in plain Vietnamese describing what failed,
`error.message` from the envelope in `body-lg`, `Thử lại` primary button, and
`error.code` in `body-sm` `on-surface-muted` (copyable — the trưởng họ will read it to
whoever helps them).

**Skeleton** — shape-matched to the real content, `surface-container` with a
`surface-container-high` sweep over `dur-5`, static tint under reduced motion. Skeletons
must occupy the **exact** final geometry: list skeletons render the real row height, the
tree renders node-shaped blocks in the real layout. Zero CLS is a pass/fail criterion
(§6, T-09).

**OfflineBar** — persistent, glass-free, `warning-container`, above the nav:
*"Đang mất kết nối. Dữ liệu bạn đang xem là bản đã lưu lúc {giờ}."*

### 4.4 Navigation and overlays

**AppBar (mobile)** — glass, 56dp + safe area, title `title-lg`, back as a 48dp icon
button, at most two trailing actions (overflow the rest).

**BottomNav (mobile)** — glass, 5 items: `Tổng quan · Cây gia phả · Thành viên · Sự
kiện · Tài khoản`. Icon 24 + label `label-md` **always visible** (icon-only nav is
unusable for an older first-time user). Active = `primary` icon + label + a
`primary-container` pill behind the icon. Height grows with text scale; labels wrap to
two lines rather than truncate.

**Sidebar (web)** — 264px, `surface-container-low`, collapsible to 72px icon rail above
1280px only; below 1024px it becomes a drawer. Clan switcher pinned at the top, user
menu at the bottom.

**ClanSwitcher** — shows clan name + role chip. Single-clan users see it as static text,
not a control. Multi-clan users get a menu; switching is a full state reset (query cache
cleared) with a `dur-4` cross-fade, because showing clan A's tree with clan B's header
for even one frame is a data-integrity failure in this product.

**BottomSheet (mobile)** / **SidePanel (web ≥1024px)** — the same content, presented per
platform. `radius-xl` top corners, `elev-3`, drag handle, scrim, focus trap, Esc /
back-gesture to close.

**Dialog** — max-width 480, `radius-xl`, `elev-3`, title `title-lg`, body `body-lg`,
actions right-aligned on web / full-width stacked on mobile, destructive action never
the default focus.

**Toast** — bottom-centre above the nav, `surface-container-highest`, `radius-pill`,
`elev-2`, 5s (never auto-dismisses an error), one action slot, `role="status"`.

**Tabs** — text labels, `title-md`, active indicator is a 3px `primary` bar (an active
indicator is a control affordance, not a section rule — exempt), scrollable when
overflowing, never truncating a Vietnamese label.

**Tooltip** — **web pointer only**. Every tooltip's content must also be reachable
without hover (a `⋯` sheet, helper text, or an info button). Mobile has no tooltips.

### 4.5 Domain components

- **GenerationBadge** — §3.2.
- **HistoricalDateDisplay** — §3.1.
- **WifeGroupHeader** — §3.3.
- **PedigreeStubChip** — §3.4.
- **FounderPrompt** — §7.4b.
- **ConflictDialog** — §7.7c.
- **RelationshipRow** — kinship term (server-localised) + person + type chip
  (`Con đẻ` / `Con nuôi` / `Con riêng`) + date range.
- **LunarLine** — §3.1.
- **CursorList** — the only list primitive. Owns: first-page skeleton, empty, error,
  `Tải thêm`, end-of-list marker, and `invalid_cursor` recovery. No screen implements
  pagination itself.
- **FieldDiff** — §7.9d. The three-way row (`base` / `proposed` / `current`) with its
  three verdicts. The single most information-dense component in the product; it
  collapses to two values when the third carries nothing.
- **TargetStateBanner** — §7.9c. Renders the `target` block (`is_stale`, `is_deleted`,
  `conflicts`) into one of four states and owns whether `Duyệt` exists at all.
- **ProposalCard** — §7.9c. Queue row: requester, target person, field count, age, and
  a triage pill computed from `target`.
- **RoleBadge** — `Quản trị` / `Biên tập viên` / `Người xem`, tonal, always text.
- **AuditRow** — §7.11: actor, action (server-localised), target, timestamp.
- **DocumentTile** — §7.12. Type icon + title render before, and without, the image.
- **ApprovalRow** — §7.10a: pending member with `Duyệt` / `Từ chối` and a role select.

---

## 5. Accessibility — testable requirements

Each is written so a person or a test can return pass/fail. These are release gates, not
aspirations.

| # | Requirement | Pass criteria |
|---|---|---|
| T-01 | Text contrast | Every text/background token pair used in the build measures ≥4.5:1, or ≥3:1 for text ≥24px or ≥19px bold. Verified by a token-pair audit script over the approved pairs list, not by spot-checking screenshots. |
| T-02 | Non-text contrast | Focus rings, selected-state indicators, and input fills measure ≥3:1 against adjacent colours. |
| T-03 | Touch targets | Every interactive element's hit box is ≥48×48dp on mobile and ≥44×44px on web pointer, including icon buttons, chips, and list-row trailing actions. Adjacent targets have ≥8dp separation. |
| T-04 | 200% text scale | Every screen in §7 renders at 320dp width with OS text scale 2.0 (web: root font-size 32px, plus 200% browser zoom) with **no clipped glyph, no overlapping element, and no horizontal page scroll**. Captured as a screenshot set per release. |
| T-05 | No fixed heights on text | No container holding user text or a localised string declares a fixed height. Enforceable by lint/grep in review. |
| T-06 | Colour is never the only channel | Every state (selected, error, precision, role, deceased, stub) carries text or an icon in addition to colour. Verified by rendering the screen set in greyscale and confirming every state is still identifiable. |
| T-07 | Keyboard operability | Every action is reachable and executable by keyboard alone, in a logical order, with a visible focus ring at every stop. **Includes the family tree** — see T-08. |
| T-08 | Tree has an accessible equivalent | The pan/zoom tree canvas is accompanied by a keyboard-navigable, screen-reader-readable list/outline view exposing the same nodes, đời values, and đa thê grouping. Toggle is visible, not hidden in settings. |
| T-09 | Zero layout shift | Cumulative Layout Shift ≤ 0.02 on every route, measured on a throttled 3G profile. Skeletons must match final geometry. |
| T-10 | No hover-only information | With a pointer-less profile, every piece of information and every action remains reachable. |
| T-11 | Reduced motion | With `prefers-reduced-motion: reduce`, no element translates or scales; opacity transitions ≤90ms; the tree does not auto-pan. |
| T-12 | Language announcement | The document/app declares `lang="vi"` (or the active locale) so diacritics are pronounced correctly; any element whose content is in a different language carries its own `lang`. |
| T-13 | Form semantics | Every field has a programmatically associated label; errors are referenced by `aria-describedby` and announced; on failed submit, focus moves to the first invalid field and a summary is announced once. |
| T-14 | đời announcement | `Đời 5` announces as "đời thứ 5"; `Đời ?` announces as "chưa xác định đời". Never a bare number, never "question mark". |
| T-15 | Date announcement | A `HistoricalDate` announces its display string, and appends "âm lịch, {lunar}" when a lunar value exists. `unknown` announces "không rõ", not silence. |
| T-16 | Images are optional | With all image requests blocked, every screen remains fully usable and no layout changes size. Avatars show initials; documents show type + filename. |
| T-17 | Error recovery is always offered | Every error state exposes a retry or an alternative next step; no dead-end screens. |
| T-18 | Timing | No auto-advancing carousel, no auto-dismissing error, no session-expiry without warning. |

---

## 6. Layout system

**Mobile (Flutter)** — single column. Content width = screen − 2×`space-5`. Breakpoint
at 600dp switches to a two-column split on tablets (list + detail). Safe areas
respected top and bottom; the glass nav bar's height is added to every scroll view's
bottom padding.

**Web** — content max-width **1200px**, centred, gutters `space-8`.

| Breakpoint | Layout |
|---|---|
| < 640 | Single column, drawer nav, mobile-equivalent screens |
| 640–1023 | Single column, wider gutters, drawer nav |
| 1024–1279 | Sidebar 264 + single content column |
| ≥ 1280 | Sidebar 264 + content, detail screens may use a 2-column split (main 1fr / aside 360) |

Grids are used only where the data is genuinely tabular (member list at ≥1024, admin
approval queue). Everywhere else layout is asymmetric flow per the mandate — the
dashboard is a deliberate two-size card flow, not a uniform 3×N grid.

---

## 7. Screen specifications

Notation per screen: **Purpose · Mobile · Desktop · States · Role · API**.

---

### 7.1 Đăng nhập / Đăng ký / Xác thực email

#### 7.1a Đăng nhập

**Purpose.** Get an existing family member into their clan in as few taps as possible,
and route them correctly afterwards.

**Mobile.** Vertically centred single column, gutters `space-5`. Top: clan-agnostic
wordmark (type only — no logo image, T-16) and `display-md` `Gia phả dòng họ`. Sub:
`body-lg` `Đăng nhập để xem gia phả dòng họ`. Then: Email field, Mật khẩu field with a
show/hide toggle (48dp, labelled `Hiện mật khẩu` / `Ẩn mật khẩu`), `Quên mật khẩu?` as a
ghost text button right-aligned, `Đăng nhập` primary `lg` full-width. Below a
`Hoặc` divider (a centred label on a background step, not a rule): `Tiếp tục với Google`,
`Tiếp tục với Apple` (iOS). Footer: `Chưa có tài khoản? Đăng ký`.

**Desktop.** Same column, max-width 440, centred in the viewport, with the page ground at
`surface` and the form on `surface-container-lowest` `radius-xl` `elev-1`. No marketing
split-screen — this is an invite-only family tool, not a SaaS signup.

**States.**
- *Loading* — button loading state; fields become read-only, not disabled (a disabled
  field loses its value announcement).
- *Wrong credentials* — banner above the form, `danger-container`, message from
  `error.message`. Fields keep their values. Password is **not** cleared.
- *403 `email_not_verified`* → route to 7.1c.
- *429 `rate_limited`* — the submit button becomes `Thử lại sau {n} giây` and counts
  down from `detail.retry_after`; the countdown is announced once, not every second.
- *503 `auth_provider_unavailable`* — `warning-container` banner:
  *"Hệ thống đăng nhập tạm thời gián đoạn. Đây không phải lỗi mật khẩu của bạn. Xin thử
  lại sau ít phút."* Explicitly not a credentials error.
- *Missing Supabase config (dev)* — existing copy retained.

**After success.** Never trust the login body's `has_pending_membership` or `clan_id`
(both are known-broken, per the integration guide). The client shows a **full-screen
brand hold** — wordmark + `Đang mở gia phả dòng họ…` — while it calls `GET /auth/me` and
`GET /me/clans`, then routes. This deliberate ~1s hold is preferable to painting a
dashboard with a possibly-wrong clan name (§9-J9).

#### 7.1b Đăng ký

**Purpose.** Join an existing dòng họ by code, or create a new one.

**Mobile.** Segmented control at the top: `Tham gia dòng họ` | `Tạo dòng họ mới`.
- *Tham gia*: Họ và tên · Email · Mật khẩu (with a plain-language strength hint, not a
  meter bar) · **Mã dòng họ** with helper *"Mã do quản trị dòng họ cung cấp, ví dụ:
  nguyen-huu-thanh-oai."*
- *Tạo mới*: Họ và tên · Email · Mật khẩu · Tên dòng họ · Mã dòng họ (auto-suggested,
  slugified live from the name, editable) with helper *"Người khác dùng mã này để xin
  tham gia dòng họ của bạn."*

**States.** Field-level validation errors for `auth.clan_id_required_for_join`,
`auth.clan_name_required_for_create`, `auth.clan_slug_taken` (inline on the slug field
with a suggested alternative), `clan_not_found` (inline on the code field:
*"Không tìm thấy dòng họ với mã này. Xin kiểm tra lại với quản trị dòng họ."*).

**Critical: registration is non-enumerating.** A `201` always routes to the same
"check your email" screen. The UI must never claim an account was created, and must
never say "email này đã được đăng ký".

> **Đã gửi thư tới hộp thư của bạn**
> Chúng tôi vừa gửi một thư tới **{email}**. Xin mở thư và bấm vào liên kết để tiếp
> tục. Nếu bạn đã có tài khoản với địa chỉ này, thư sẽ hướng dẫn bạn đặt lại mật khẩu.
> [Gửi lại thư] [Về trang đăng nhập]

`Gửi lại thư` has a 60s cooldown shown as `Gửi lại sau {n} giây`.

#### 7.1c Xác thực email

Two surfaces:

1. **Blocked-at-login** (`403 email_not_verified`): full screen, `heritage-container`
   icon block, `headline` `Xin xác thực email trước`, `body-lg` explanation, primary
   `Gửi lại thư xác thực`, ghost `Đổi địa chỉ email` → support/admin contact.
2. **Landing from the email link**: three states in one screen — *Đang xác thực…*
   (spinner + text, no skeleton, this is genuinely a wait), *Xác thực thành công* →
   `success-container`, auto-route to login after 3s with a manual `Đăng nhập ngay`, and
   *Liên kết đã hết hạn* → `warning-container` + `Gửi lại thư xác thực`.

**Open risk.** The landing URL parameter shape (`token_hash`+`type` vs PKCE `?code=`)
is unresolved in the contracts. The screen is designed to handle both and to show the
expired state on any failure rather than a raw error.

**Role.** N/A — pre-authentication.

---

### 7.2 Chờ duyệt · Chọn dòng họ · Dòng họ bị tạm ngưng

#### 7.2a Chờ duyệt (pending approval)

**Purpose.** Tell a person who has done everything right that they are waiting on a
human, and give them something to do.

This is not an error and must not look like one. `heritage-container` ground, generous
whitespace.

**Mobile / Desktop.** Same centred column (max-width 520 on desktop).
- `display-md` **Đang chờ quản trị dòng họ duyệt**
- `body-lg` *"Bạn đã gửi yêu cầu tham gia **dòng họ {clan_name}**. Quản trị dòng họ sẽ
  xem xét và duyệt trong thời gian sớm nhất. Chúng tôi sẽ gửi thông báo ngay khi bạn
  được duyệt."*
- A quiet three-step progress list (this **is** a real sequence, so numbering carries
  information): `1. Tạo tài khoản ✓` · `2. Gửi yêu cầu tham gia ✓` ·
  `3. Chờ quản trị duyệt ◦`
- Actions: `Kiểm tra lại` (refetches `GET /auth/me`), `Tham gia dòng họ khác`
  (`POST /auth/onboard`), `Đăng xuất` as ghost.

**States.** *Checking* — `Kiểm tra lại` in loading state. *Still pending* — toast
`Yêu cầu của bạn vẫn đang chờ duyệt.` *Approved on refetch* — success toast and
immediate route to the dashboard. *No membership at all* (`is_approved` false,
`has_pending_membership` false, `clan_id` null) → onboarding variant of this screen with
the join/create segmented control from 7.1b.

**Note.** A pending user *can* accept an invitation and can call `POST /auth/onboard`,
so those two paths stay live here; everything clan-scoped is absent, not disabled.

#### 7.2b Chọn dòng họ (clan picker)

**Purpose.** For members of more than one dòng họ, choose the active one. Reached on
first login with >1 clan, from `400 multiple_clans_no_selection`, and from the clan
switcher.

**Mobile.** Full screen, `display-md` `Chọn dòng họ`, `body-lg` *"Bạn là thành viên của
{n} dòng họ. Xin chọn dòng họ bạn muốn xem."* Then a stack of large tap targets (min
88dp): clan name in `title-lg` Jakarta, role chip (`Quản trị` / `Biên tập` /
`Người xem`), `body-md` `Tham gia từ {joined_at}`, chevron. Selected clan carries a
check and `primary-container` ground.

**Desktop.** Same list, max-width 560, centred; two columns at ≥1280 if >6 clans.

**States.** *Loading* — three shape-matched row skeletons. *Error* — `ErrorState` with
retry. *Empty* — cannot legitimately happen for an approved user; if `/me/clans` returns
`[]` the user is pending, so route to 7.2a rather than showing an empty picker.
*Selecting* — the tapped row shows an inline ring; the rest dim to 0.6; on success, full
cache reset then dashboard.

**Rule.** The picker is never skipped for multi-clan users, and the previously selected
clan is remembered per device.

#### 7.2c Dòng họ bị tạm ngưng (`clan_suspended`)

Full screen, `warning-container`. `headline` `Dòng họ {clan_name} đang tạm ngưng`,
`body-lg` explanation, `error.message` from the envelope, and — this is the important
part — `Chuyển sang dòng họ khác` when `/me/clans` has other entries, otherwise
`Đăng xuất`. Never a dead end (T-17).

---

### 7.3 Trang chủ / Dashboard

**Purpose.** In one screen: what is coming up in the family calendar, what changed, and
the three or four things this person actually does.

**Mobile.** Scrolling column:

1. **Greeting block** — `title-lg` `Chào {tên gọi}`, `body-md` `Dòng họ {clan_name} ·
   {role}`. No avatar-heavy header.
2. **Sắp tới** — the single most valuable card in the product. Up to 3 upcoming events
   from `GET /events/upcoming`, each a row: event-type icon, title `title-md`, solar
   date, lunar line when present, and a `còn {n} ngày` chip. Giỗ entries carry the
   `heritage` family. `Xem tất cả` ghost link.
3. **Quick actions** — 2×2 of large tonal tiles, filtered by role:
   `Cây gia phả` · `Thành viên` · `Thêm thành viên` (editor+) · `Ảnh & tài liệu`.
4. **Dòng họ trong số liệu** — three stat tiles: `Thành viên`, `Số đời`, `Sự kiện năm
   nay`. `tabular-nums`, `display-md` figure over `label-md` caption.
5. **Cần bạn xử lý** (admin only) — pending approvals count, identity claims count,
   and the thủy tổ prompt if the clan has no founder. `heritage-container` when it
   contains the founder prompt, `info-container` otherwise.

**Desktop.** Sidebar + 12-column content. Asymmetric by design: `Sắp tới` occupies a
7-column card on the left; `Cần bạn xử lý` + stats stack in a 5-column right rail;
quick actions become a single row of four wide tiles below. Not a uniform grid.

**States.** *Loading* — skeletons matching each card's real geometry; the greeting
renders immediately from cached profile. *Empty events* — `Chưa có sự kiện nào sắp
tới.` + `Thêm sự kiện` (editor+) or nothing (viewer). *Empty clan (0 persons)* — the
whole page collapses to a single onboarding card: `Bắt đầu dựng gia phả` →
`Thêm người đầu tiên` (admin/editor) / `Dòng họ chưa có dữ liệu. Xin chờ quản trị dòng
họ bắt đầu.` (viewer). *Partial failure* — each card fails independently with its own
inline retry; one dead endpoint never blanks the dashboard. *Offline* — OfflineBar +
cached content with a `Cập nhật lúc {giờ}` line.

**Role.** Viewer sees 1, 2, 4 and a two-tile quick-action row. Editor adds
`Thêm thành viên`. Admin adds card 5 and the admin nav item.

---

### 7.4 Cây gia phả

The hardest screen, and the one where web and mobile diverge most.

**Purpose.** Let someone see where a person sits in the lineage — đời, cha/mẹ, các bà
vợ, con cháu — and move along it without getting lost.

#### 7.4a The tree itself

**Desktop.** Pan/zoom canvas.
- Nodes are `PersonNodeCard`s laid top-down by đời. Left rail shows a **đời ruler**:
  sticky labels `Đời 1 · Đời 2 · …` aligned to each row band; bands alternate between
  `surface` and `surface-container-low` — that background step is the only separator
  (no-line rule).
- Connectors are 2px `secondary` @ 40% curves. These are data relations, not section
  rules, so they are exempt from the no-line rule.
- Floating glass toolbar, bottom-centre: `−` `100%` `+` · `Vừa khung` · `Chế độ danh
  sách` · `Xuất gia phả` (admin only — see below). Exactly one glass surface on this
  screen.

  **Correction to the first draft of this spec.** This toolbar previously carried
  `Xuất PDF`, taken from the `Export tree as PDF` row in `rbac.md`. That row is an
  aspirational permission with **no endpoint behind it** — PDF export is deferred by
  ADR-020, depends on the unbuilt worker of ADR-005 and the unbuilt Redis of ADR-004,
  and `format=pdf` would 422 today. Drawing it was the same mistake this spec refused
  to make for `Đề nghị sửa`. The button is replaced by `Xuất gia phả` (§7.14), which is
  **admin-only** and produces JSON or GEDCOM. See §9-J22.
- Right side panel (≥1280) shows the selected person's summary and
  `Xem hồ sơ đầy đủ →`.
- Depth control: `Hiển thị {n} đời` slider, 1–10, default 5 (not the API's 10 — ten đời
  of a real clan is thousands of nodes over 3G).
- Keyboard: arrow keys move between siblings/parent/children, `Enter` opens the sheet,
  `+`/`−` zoom, `Home` returns to thủy tổ. Focus ring on the focused node at all times.

**Mobile.** **Not a pan/zoom canvas.** A pinch-zoom graph on a 5-inch screen at 200% text
scale is unusable, and it is exactly the older user who most needs this screen. Mobile
uses a **focus navigator** built on `GET /tree/focus/{id}`:

- Top: breadcrumb of ancestors as a horizontally scrollable chip row
  `Thủy tổ › Đời 2 Nguyễn Hữu Đàm › Đời 3 …`, tappable to re-root.
- Middle: the focused person as a large `PersonNodeCard` (full width), with `Cha`/`Mẹ`
  compact rows above it.
- Below: `Con cái` grouped by wife per §3.3, each child a tappable row that re-roots the
  view (`dur-3` slide).
- `has_more_descendants` on a boundary node renders `Còn {…} đời nữa →`.
- Bottom glass bar: `Về thủy tổ` · `Tìm quan hệ` · `Chế độ cây` (a read-only, zoomable
  overview for users who want it, explicitly secondary).

**đa thê rendering** (both clients). Under a father with two wives:

```
Đời 4 · Nguyễn Hữu Đàm  [Thủy tổ chip if applicable]
├─ Vợ cả · Trần Thị Mão        ← WifeGroupHeader, surface-container-low band
│   ├─ Nguyễn Hữu Lộc   Đời 5
│   └─ Nguyễn Thị Sen    Đời 5
├─ Vợ hai · Lê Thị Nhàn        ← second band, same weight, same node size
│   └─ Nguyễn Hữu Trác  Đời 5
└─ Chưa rõ mẹ                   ← only when mother_id is null
    └─ Nguyễn Hữu Bảo   Đời ?
```

**Null đời rendering.** Any node whose `generation` is null shows `Đời ?` (§3.2). On
desktop, nodes with null đời cannot be placed on the đời ruler, so they render in a
**separate tray** below the canvas headed `Chưa nối vào thủy tổ ({n})` — placing them
in a đời band would be a guess, and dropping them would hide real people (§9-J3).

**Pedigree-collapse stubs.** Per §3.4.

#### 7.4b Chưa có thủy tổ — `404 clan_founder_not_found`

**This is an onboarding state, not an error.** No error iconography, no red, no "không
tìm thấy".

Centred card on the tree canvas, `heritage-container`, `radius-xl`:

> **Dòng họ chưa có thủy tổ**
> Cây gia phả được dựng từ thủy tổ — người khởi đầu dòng họ. Xin chọn một người trong
> danh sách thành viên làm thủy tổ để bắt đầu dựng cây. Bạn có thể đổi lại sau.
>
> *(admin)* [Chọn thủy tổ] [Thêm người đầu tiên]
> *(editor / viewer)* Quản trị dòng họ cần chọn thủy tổ trước khi cây gia phả hiển
> thị được. [Xem danh sách quản trị]

`Chọn thủy tổ` opens a searchable person picker (sheet on mobile, dialog on web) →
`PUT /clans/me/founder`. Confirmation is required and names the person:
*"Đặt **{tên}** làm thủy tổ của dòng họ {clan_name}?"*

**The same state reappears** if the current founder is soft-deleted. The copy then adds:
*"Thủy tổ trước đây đã bị xóa khỏi gia phả."* with two admin actions —
`Khôi phục {tên}` (`POST /persons/{id}/restore`) and `Chọn thủy tổ khác`. Two paths,
because the backend genuinely has two recovery paths.

#### 7.4c Other states

*Loading* — node-shaped skeletons in a plausible đời layout, đời ruler already drawn
(no shift). *Large tree* — beyond ~300 rendered nodes, show a banner
*"Cây gia phả rất lớn. Đang hiển thị {n} đời."* with a depth control, rather than
attempting to draw everything. *Error* — `ErrorState` with retry and a
`Chế độ danh sách` fallback. *Offline* — last successfully loaded tree, OfflineBar,
navigation limited to cached nodes.

**Role.** Viewer: no long-press edit actions, no `Chọn thủy tổ`, and **no export
control** — `GET /exports/clan` is admin-only. Viewer and editor get `Đề nghị sửa` on
the node sheet (§7.9a); admin additionally gets `Xuất gia phả`.

---

### 7.5 Danh sách thành viên

**Purpose.** Find a person by name in a clan of several hundred, and see enough to know
it is the right one.

**Mobile.** Sticky glass header: SearchField + a `Bộ lọc` chip showing the active count.
Body: `CursorList` of `PersonRow` (avatar 40, name `title-md`, second line
`{năm sinh} – {năm mất}` or `Sinh {…}`, trailing đời badge). Filter sheet:
`Đời` (multi-select chips incl. `Chưa xác định`), `Giới tính`, `Còn sống / Đã mất`,
`Chi/nhánh`. FAB `+ Thêm thành viên` (editor+).

**Desktop (≥1024).** This data **is** tabular, so a table is allowed here: columns
`Họ và tên` · `Đời` · `Năm sinh` · `Năm mất` · `Chi/nhánh` · `Cập nhật`. Row separation
is by `space-2` gap and a `surface-container-low` row ground, not by rules; in
high-contrast mode `outline-variant` @15% row separators are permitted (the mandate's
own exception). Sticky header row. Left rail carries the filters as a persistent panel
rather than a sheet.

**Pagination — cursor only.** There is no page number anywhere in the UI, because the
API has no concept of one.
- Mobile: auto-loads the next page when the sentinel is 400px from the viewport, **and**
  always renders a real `Tải thêm` button at the end — on 3G the auto-load frequently
  fails and the user needs something to press.
- Web: an explicit `Tải thêm` button only. Infinite scroll on desktop breaks keyboard
  users and hides the page footer.
- `has_more: false` → an end marker `Đã hiển thị hết {n} thành viên.`
- `400 invalid_cursor` → silently drop the cursor, refetch page 1, preserve scroll
  position, no visible error. The user did nothing wrong.

**States.**
- *First load* — 8 shape-matched row skeletons.
- *Loading next page* — 2 skeleton rows appended below existing content; existing rows
  never move.
- *Searching* — existing results stay visible at 0.6 opacity with a ring in the search
  field. Result count announced politely: `{n} kết quả`.
- *Empty (no members)* — `Dòng họ chưa có thành viên nào` + `Thêm thành viên đầu tiên`
  (editor+) / an explanation (viewer).
- *Empty (no search results)* — `Không tìm thấy "{query}"` + `Xóa bộ lọc` and, for
  editor+, `Thêm "{query}" làm thành viên mới`.
- *Error* — `ErrorState`; already-loaded pages remain visible above it.
- *Offline* — cached first page + OfflineBar; `Tải thêm` disabled with the reason stated
  in text.

**Role.** Viewer: no FAB, no row-level `⋯` actions. Admin: row `⋯` gains `Xóa` and
`Đặt làm thủy tổ`.

---

### 7.6 Hồ sơ một người

**Purpose.** Everything known about one person, honestly — including how much is
uncertain.

**Mobile.** Scrolling column:

1. **Header** — avatar 96 centred, name `headline` Jakarta, đời badge + role/status
   chips (`Thủy tổ`, `Đã mất`, `Con nuôi` where applicable), and the life line:
   `1892 – khoảng 1961` with precision chips. Actions per role (§3.5).
2. **Tên gọi** — only the name fields that exist: `Tên húy`, `Tên tự`, `Tên thụy`,
   `Biệt hiệu`, `Chức tước`. Each is a label/value pair; absent fields are omitted, not
   shown as empty. Vietnamese name types carry a small info affordance explaining what
   each means — most users have never had to distinguish tên tự from tên thụy.
3. **Ngày tháng** — birth and death, each rendered by `HistoricalDateDisplay` with its
   precision chip and lunar line. **This is where all four precisions must coexist
   gracefully** and it is the profile's design test:
   - `Ngày sinh · 15/08/1948` (exact)
   - `Ngày mất · khoảng 1961` `[khoảng]` / `Âm lịch · 20/11 Tân Sửu`
   - `Ngày sinh · 1892` `[năm]`
   - `Ngày mất · Không rõ` `[không rõ]`
4. **Nơi chốn** — nơi sinh, nơi mất, nơi cư trú.
5. **Quan hệ** — `Cha mẹ`, `Vợ/chồng` (with `Vợ cả`/`Vợ hai` order chips and marriage
   status), `Con cái` **grouped by mother per §3.3**, `Anh chị em`. Each row navigates.
6. **Ảnh & tài liệu** — horizontal thumbnail strip; each item shows type icon + title,
   so it reads correctly before (or without) the image. Presigned URLs expire in one
   hour: on a 403 the client refetches `GET /documents/{id}` once, and the thumbnail
   shows a `Tải lại` affordance rather than a broken image.
7. **Tiểu sử** — `body-lg`, max ~65 characters per line, `Xem thêm` past 6 lines.
8. **Ghi chú** and, for admin, an audit line `Cập nhật lần cuối {…} bởi {…}`.

**Desktop (≥1280).** Two columns: main 1fr (dates, places, biography, documents) and a
360px aside (header card, relationships, quick actions). Below 1280 it collapses to the
mobile order.

**States.** *Loading* — full shape-matched skeleton including the avatar circle.
*Not found / cross-clan* — 404 renders `Không tìm thấy người này trong dòng họ
{clan_name}.` with `Về danh sách thành viên` — never leaks that the person may exist in
another clan. *Soft-deleted (admin view)* — a `warning-container` banner
*"Người này đã được xóa khỏi gia phả ngày {…}."* + `Khôi phục`; all content read-only.
*Sparse record* — a person with nothing but a name is valid and must look intentional:
sections 2–8 collapse and one line reads *"Gia phả hiện chỉ ghi tên. Bạn có thể bổ sung
thông tin."* (editor+).

**Role.** Per §3.5. Viewer sees the permanent role line and no buttons.

---

### 7.7 Thêm / Sửa người

**Purpose.** Let an editor record what the gia phả actually says — including what it
says vaguely — without fighting the form.

**Mobile.** Full-screen form, sectioned, with a sticky bottom action bar (`Hủy` ghost /
`Lưu` primary) that sits above the keyboard.

**Desktop.** Dialog at ≥1024 (max-width 720) for create; full page for edit, with the
same sticky footer.

**Sections.** `Tên gọi` (Họ và tên required; the four Vietnamese name types in a
collapsed `Tên gọi khác` group) · `Giới tính` (segmented: Nam / Nữ / Không rõ) ·
`Ngày sinh` (HistoricalDateField) · `Ngày mất` (HistoricalDateField, revealed by an
`Đã mất` switch) · `Nơi chốn` · `Chi/nhánh` · `Tiểu sử` · `Ghi chú`.

**Copy that matters.** The precision control's helper text is the whole point of the
product:

> Gia phả cũ thường không ghi ngày chính xác. Hãy chọn đúng mức chắc chắn mà gia phả
> ghi — "khoảng 1750" là một câu trả lời đúng, không phải câu trả lời thiếu.

#### 7.7a Validation and warnings

- Client-side: required `Họ và tên`; year plausibility (1000–current+1); death not
  before birth when both are exact.
- `422 relationship.parent_too_young` → inline error on the relationship field with
  `detail.min_age_gap` and `detail.actual` spelled out in Vietnamese.
- `meta.warning` on a successful write (unusual age gap, low gap on estimated dates) →
  the save **succeeds**, and a `warning` toast appears afterwards:
  *"Đã lưu. Lưu ý: chênh lệch tuổi giữa cha/mẹ và con là {n} năm — xin kiểm tra lại nếu
  đây là nhầm lẫn."* A warning never blocks a save.
- Unsaved-changes guard on back/close: *"Bạn có thay đổi chưa lưu. Thoát và bỏ thay
  đổi?"*

#### 7.7b Save states

*Idle* → *Submitting* (button loading, fields read-only) → *Success* (toast
`Đã lưu thay đổi.` + return) or an error state. On network failure the form retains
everything and offers `Thử lại` — the user's typing is never lost.

#### 7.7c `409 stale_write` — "người khác vừa sửa"

The most important error dialog in the product. Two people editing the same ancestor is
normal in an active clan.

Dialog, `radius-xl`, max-width 560, **not** dismissible by scrim tap:

> **Người khác vừa sửa hồ sơ này**
> Trong lúc bạn đang nhập, một người khác đã cập nhật hồ sơ **{tên}**. Xin chọn giữ lại
> nội dung nào cho từng mục.

Body: a **field-level comparison list showing only the fields that actually differ** —
not a full-record diff. Each row:

```
Ngày mất
  Bản của bạn      khoảng 1961      [Giữ bản của tôi]  ← default when the user edited this field
  Bản mới nhất     15/11/1961       [Dùng bản mới]     ← default when the user did not
```

Selection is a two-option segmented control per field, so both choices are always
visible and neither is hidden behind a colour.

Actions: `Lưu bản đã chọn` (primary) · `Bỏ thay đổi của tôi, tải lại` (ghost) ·
`Sao chép nội dung của tôi` (ghost — the escape hatch when the user just wants their
text back).

Behaviour: on open, refetch the record for current values and `version`; on save,
resubmit with the fresh `expected_version`. **Never auto-resubmit** and never retry with
the stale version. If the resubmit 409s again, reopen the dialog with the newer data and
add *"Hồ sơ này đang được nhiều người sửa cùng lúc."*

Mobile presents the same content as a full-screen sheet, one field per card. See §9-J6
for why this is field-level rather than a three-way merge.

**Role.** Editor and admin only. A viewer never reaches this screen; if a role is
downgraded mid-edit, the save returns 403 and the dialog explains it plainly with a
`Sao chép nội dung của tôi` escape.

---

### 7.8 Sự kiện / Giỗ chạp

**Purpose.** The clan's calendar of giỗ, sinh nhật, kỷ niệm and việc họ — the screen that
gets opened most often by the people who use the product least.

**Mobile.** Tabs: `Sắp tới` | `Cả năm`.
- *Sắp tới* — chronological cards from `GET /events/upcoming`. Each: event-type icon in
  a tonal circle (giỗ uses `heritage-container`), title `title-md`, person link,
  solar date `dd/MM/yyyy`, lunar line when applicable, `còn {n} ngày` chip (`Hôm nay` /
  `Ngày mai` for 0/1), and `Hằng năm` chip when recurring.
- *Cả năm* — a month-grouped list, not a calendar grid. A 7-column month grid at 200%
  text scale on a 320dp screen cannot show a Vietnamese event title; the list can.
  Sticky month headers `Tháng 8, 2026`.
- FAB `+ Thêm sự kiện` (editor+).

**Desktop.** Two columns: a month calendar grid on the left (≥1024, where the grid does
fit) and the upcoming list on the right. Days with events carry a filled dot per event
type; selecting a day filters the right column. The list is authoritative; the grid is
navigation.

**Two different lunar concepts, never conflated** (§9-J7):

| | Source | Label in UI |
|---|---|---|
| `HistoricalDate.lunar` | User-entered text, verbatim, never computed | `Âm lịch (ghi trong gia phả)` |
| Next lunar occurrence | Backend-computed (ADR-018, Hồ Ngọc Đức, UTC+7) | `Giỗ năm nay · {dd/MM/yyyy} dương lịch` |

An event card for a giỗ therefore reads:

```
Giỗ cụ Nguyễn Hữu Đàm            [Hằng năm] [Giỗ]
Âm lịch · 20/11
Giỗ năm nay · 29/12/2026 (dương lịch)      còn 12 ngày
```

**Event form** (editor+): Loại sự kiện (Ngày giỗ / Sinh nhật / Kỷ niệm ngày cưới /
Lễ việc họ / Tùy chỉnh) · Tiêu đề · Người liên quan (person picker) · Ngày (a
HistoricalDateField) · `Tính theo âm lịch` switch · `Lặp lại hằng năm` switch ·
`Nhắc trước {n} ngày` · Mô tả.

**The precision trap, designed for.** A recurring event whose `event_date_precision` is
not `exact` is stored and listed but **never notified and never surfaced in
`/events/upcoming`**. Silence would be a broken promise, so the form warns at input
time, inline under the recurrence switch, as `warning-container`:

> Ngày này được ghi là **{khoảng 1950}**. Vì chưa có ngày chính xác, hệ thống sẽ **không
> gửi nhắc hằng năm** cho sự kiện này. Sự kiện vẫn được lưu và hiển thị trong danh sách.

The same notice appears as a chip `Không nhắc tự động` on the event card in the list,
so a user who set it months ago is not left wondering.

**States.** *Loading* — 4 card skeletons. *Empty upcoming* — `Không có sự kiện nào trong
{n} ngày tới.` + `Thêm sự kiện` (editor+). *Empty year* — `Dòng họ chưa ghi sự kiện
nào.` with an explanation of what giỗ tracking does. *Error* — `ErrorState`. *Offline* —
cached upcoming list + OfflineBar; `còn {n} ngày` recomputed from the device clock and
labelled `Tính theo giờ máy`.

**Role.** Viewer: no FAB, no per-card `⋯`. Editor and admin may create, edit and delete
events (RBAC allows editors to delete events).

---

### 7.9 Đề nghị sửa — change requests

**Purpose.** Close the loop that J5 could not: the people who know a birth date is wrong
are the relatives reading the tree, not the two or three members with edit rights. A
viewer proposes a correction to a person, field by field; an editor or admin reviews it.

Backed by `POST/GET /change-requests`, `…/{id}/approve`, `…/{id}/reject`
(`docs/contracts/rest-change-requests-api.md`, ADR-037). Scope in v1 is
`action="update"` on `resource_type="person"` — the UI never exposes an action or
resource picker, because there is nothing to pick.

**Who sees what.** Submitting is open to every approved member; in practice viewers.
Reviewing is **editor or admin** — an editor can already make the same edit
unilaterally, so gating on admin would protect nothing and would stall the queue. A
viewer sees only their own proposals on both list and detail; someone else's returns
`404`, and the UI says "không tìm thấy", never "bạn không có quyền".

#### 7.9a Gửi đề nghị (the viewer's submit flow)

**Entry.** From the person profile a viewer now has a real header action,
`Đề nghị sửa` (tonal, not primary — reading is still the main job on that screen). Each
value row in `Ngày tháng`, `Tên gọi` and `Nơi chốn` additionally offers
`Đề nghị sửa mục này` on tap/`⋯`, which opens the same form with that one field
pre-selected. Also reachable from the tree node sheet.

**The form is the edit form.** The contract fixes `changes` to exactly the
`PATCH /persons/{id}` body minus `expected_version`, explicitly "so a client can render
one form for both". So §7.7's form is reused wholesale, including
`HistoricalDateField`, with four differences:

1. Header reads `Đề nghị sửa hồ sơ {tên}`, submit reads `Gửi đề nghị`.
2. Every field starts at the record's current value and is visually marked once
   touched — a `Đã sửa` chip on the field label and a running count in the sticky bar:
   `Gửi đề nghị (2 mục)`. Only touched fields go into `changes`; an untouched field is
   never proposed, which is what keeps `base_values` small and the merge (§7.9d) loose.
3. A `note` field at the bottom, `Vì sao bạn cho rằng cần sửa?`, multiline, optional but
   **visually encouraged** (helper: *"Ví dụ: gia phả chép tay trang 12 ghi năm Canh
   Thân."*). Reviewers act on evidence; an unexplained proposal is a guess.
4. **`Số điện thoại` and `Email` are absent from the form**, not disabled — they are not
   proposable, and the reason is worth one line rather than a mystery:
   *"Số điện thoại và email không đề nghị sửa được — đây là thông tin liên lạc, không
   phải nội dung gia phả."* `avatar_url` is likewise absent (it is server-managed).

**Submit gating.** `Gửi đề nghị` stays disabled until at least one field differs from
the record, so `422 change_request.no_changes` is unreachable by construction. This is
the one place a disabled control is correct — it is a transient form state, not a
permission (§4.1).

**Success.** Not a toast — a full confirmation, because the user needs to know a human
is now involved:

> **Đã gửi đề nghị**
> Đề nghị sửa hồ sơ **Trần Đình Đàm** đã được gửi tới quản trị và biên tập viên của dòng
> họ. Bạn sẽ thấy kết quả trong mục **Đề nghị của tôi**.
> [Xem đề nghị của tôi] [Về hồ sơ]

There is **no notification** when a proposal is submitted or reviewed (ADR-037 defers
it), so the confirmation must not promise one. "Bạn sẽ thấy kết quả trong mục Đề nghị
của tôi" is true; "chúng tôi sẽ báo cho bạn" would not be. See §9-J16.

**Errors.** `404 person_not_found` (target deleted while the form was open) →
`warning-container` banner *"Người này vừa được xóa khỏi gia phả nên không gửi đề nghị
được."* with the text preserved and a `Sao chép nội dung của tôi` escape.
`422 change_request.field_not_submittable` should be unreachable; if it fires, the
inline error names `detail.fields` rather than showing a raw code.

#### 7.9b Đề nghị của tôi (the requester's own list)

**Purpose.** The requester asked a question of the clan; this is where the answer lands.

**Mobile.** Tabs `Đang chờ` | `Đã duyệt` | `Bị từ chối` (mapping to `status`), a
`CursorList` of cards. Each card: target person (avatar + name + đời), the proposed
fields as chips (`Ngày mất`, `Nơi sinh`), the note excerpt, and relative age
(`Gửi 3 ngày trước`). Resolved cards additionally carry the outcome:

- Approved — `success-container` strip, `Đã được duyệt · bác Vinh · 12/08`, plus
  `review_notes` when present, and `Xem hồ sơ` to see the applied result.
- Rejected — `surface-container-high` (**not** `danger`), `Không được duyệt · bác Vinh ·
  12/08` and the `review_notes` verbatim. A declined suggestion from a relative is not
  an error and must not be coloured like one (§9-J15).

**Desktop.** Same list at max-width 720 in the content column; no table — these are
prose-carrying items, not tabular data.

**There is no withdraw action**, because there is no endpoint for one. The UI does not
draw a `Thu hồi` button it cannot honour; a pending card instead reads
*"Đang chờ quản trị hoặc biên tập viên xem xét."* Flagged in §9-J16.

**States.** *Loading* — 3 card skeletons. *Empty* — `Bạn chưa gửi đề nghị nào.` plus one
line explaining what the feature is for and `Xem cây gia phả`. *Error* — `ErrorState`.

#### 7.9c Hàng đợi đề nghị (the reviewer's queue)

**Purpose.** Let a busy trưởng họ triage on a phone in under a minute, and never open a
proposal only to find it cannot be actioned.

**Entry.** On web, a sidebar item `Đề nghị sửa` for editor+ with a pending count badge.
On mobile the bottom nav's five slots are all spoken for, so the entry is a counted chip
in the dashboard app bar (`✎ 3`) — the slot the removed notification bell used to occupy
(§9-J24) — plus the `Cần bạn xử lý` dashboard card (§7.3 card 5). The queue is a pushed
route with a back arrow, not a nav destination, on mobile.

**Mobile.** Filter chips `Đang chờ` (default) | `Đã duyệt` | `Bị từ chối`, then a
`CursorList` of `ProposalCard`s:

```
Trần Đình Đàm            Đời 2        [Sẵn sàng duyệt]
2 mục · Ngày mất, Nơi mất
"Gia phả chép tay trang 12 ghi năm Canh Thân"
anh Hải · 3 ngày trước
```

**The triage pill is computed from `target`, and it is the whole point of the card.**
It is what stops a reviewer opening ten proposals to find the two they can act on:

| `target` | Pill | Colour |
|---|---|---|
| `is_deleted: true` | `Người đã bị xóa` | `warning` |
| `conflicts` non-empty | `Có xung đột ({n} mục)` | `danger` |
| `is_stale: true`, `conflicts: []` | `Sẵn sàng duyệt` | `success` |
| not stale | `Sẵn sàng duyệt` | `success` |

Note the last two rows are deliberately identical. `is_stale` alone is the *normal,
harmless* case — somebody edited a different field — and approval still succeeds with
both edits surviving. Surfacing it as a warning would train reviewers to fear a
non-event. See §9-J14.

**Desktop.** Two-pane at ≥1280: queue list 380px on the left, review detail on the
right, so a reviewer with a screen can work the queue without navigating. Below 1280 it
is list → detail like mobile.

**States.** *Loading* — 4 card skeletons. *Empty pending* — `Không có đề nghị nào đang
chờ.` plus, on first-ever use, one line explaining that members can now propose
corrections. *Empty approved/rejected* — plain. *Error* — `ErrorState`.
`400 invalid_cursor` → drop and refetch silently, per §3.6.

**Role.** Viewers never see this nav item; if they deep-link, the same route renders
§7.9b (their own proposals) rather than an error — the API scopes them to their own
rows anyway, so the honest UI is "this is your list", not "access denied".

#### 7.9d Xem xét một đề nghị — the three-value comparison

**Purpose.** Show the reviewer exactly what would change and what it would overwrite,
on a phone, without a spreadsheet.

**Layout, top to bottom.**

1. **Target header** — avatar, person name (`title-lg`, links to the profile), đời badge.
2. **Provenance** — `anh Hải đề nghị · 3 ngày trước`, and the `note` in `body-lg` on
   `surface-container-low`. The note is the reviewer's evidence; it is not a footnote.
3. **TargetStateBanner** (§7.9e) — only when it has something to say.
4. **The field list** — one `FieldDiff` per proposed field.
5. **Sticky action bar** — `Duyệt` primary + `Từ chối` ghost, or per §7.9e.

**FieldDiff — three values, shown only when the third means something.** The API always
sends `base`, `proposed`, and (via the target snapshot) `current`. Rendering all three
every time would be honest and unusable: on the common path `base == current` and the
third column is pure noise on a 360dp screen. So the component has three renderings,
one per merge verdict (ADR-037 §5):

*Verdict A — `current == base` (nobody touched this field). Two values:*

```
Ngày mất
  Hiện tại        khoảng 1851   [khoảng]
  Đề nghị sửa     15/11/1851
```
`surface-container-low`, neutral. The proposed value is the emphasised one.

*Verdict B — `current == proposed` (someone already made this exact correction).
Informational, deemphasised, and it still approves:*

```
Nơi mất                                    [Đã sửa rồi]
  Gia phả hiện đã ghi   Làng Hành Thiện, Nam Định
  Đề nghị này cũng ghi đúng như vậy — duyệt sẽ không đổi gì thêm.
```
`surface-container`, `on-surface-variant`. This case is why the merge is loose; showing
it as a change would be a lie.

*Verdict C — conflict (`current` is neither). All three, and this is where the design
spends its contrast:*

```
Ngày mất                                   [Xung đột]
  Lúc gửi đề nghị      1919                        ← base
  Người đề nghị muốn   khoảng 1920                 ← proposed
  Gia phả hiện ghi     31/12/1921  · bác Vinh sửa  ← current, emphasised
```
`danger-container`, and the **`current` row is the visually dominant one** — it is the
value that would be destroyed, and it is the reason the button is gone.

**Ordering is by verdict, not by field order: conflicts first, then real changes, then
already-applied.** A reviewer scanning a phone must hit the blocker before the noise.

**Section counts** above the list: `1 xung đột · 2 thay đổi · 1 đã sửa rồi`, `tabular-nums`.

**Dates inside a diff** are rendered by `HistoricalDateDisplay` (§3.1) from the scalar
`birth_date` / `_precision` / `_display` triple that `changes` and `conflicts` carry —
**not** the `HistoricalDate` object. This is the contract's one documented shape
exception and the diff component is the only place in the product that must know about
it. See §9-J17.

**Actions.**
- `Duyệt` — confirmation dialog naming the person and the count:
  *"Duyệt đề nghị và cập nhật hồ sơ **Trần Đình Đàm** (2 mục)?"* On success: toast
  `Đã duyệt và cập nhật hồ sơ.` and return to the queue with the row moved to `Đã duyệt`.
- `Từ chối` — sheet (mobile) / dialog (web) with an optional `review_notes` field,
  helper *"Lời nhắn này hiển thị cho người đã gửi đề nghị."* A rejection with a reason
  is the difference between a relative contributing again and not.

**A consequence to surface.** Approval advances the person's `version` exactly as a
`PATCH` would, so a reviewer who also has that person open in an edit form elsewhere
will get `409 stale_write` (§7.7c) on their next save. That is correct and already
designed for; the approve confirmation does not need to mention it, but the two flows
must not be merged.

**States.** *Loading* — header + three `FieldDiff`-shaped skeletons. *Already reviewed*
(`409 change_request.not_pending`, or arriving at a resolved id) — the same comparison
rendered read-only with an outcome strip and no action bar; `conflicts` is `[]` on
reviewed proposals, so verdict C never appears here. *Offline* — read-only with the
action bar replaced by *"Cần kết nối mạng để duyệt hoặc từ chối."*

#### 7.9e Không duyệt được — the blocked and conflict states

The contract is explicit that clients gate the Approve affordance on `conflicts` and
`is_deleted`, and that the `target` block exists so a reviewer is warned **before** they
press. So the rule is: **`Duyệt` is absent, not disabled, whenever it would fail.**

**Conflict** (`conflicts` non-empty, or a `409 change_request.target_conflict` returned
by a race between load and press):

> **Không duyệt được — hồ sơ đã thay đổi**
> Kể từ khi đề nghị này được gửi, **1 mục** đã được người khác sửa sang một giá trị
> khác. Duyệt bây giờ sẽ xóa mất thay đổi mới hơn đó, nên hệ thống không cho duyệt.

`danger-container`. Actions offered, both from the contract's recommended flow:

1. `Từ chối đề nghị` — the newer value stands. Pre-fills `review_notes` with a
   suggested, editable sentence naming the field:
   *"Hồ sơ đã được cập nhật ngày mất là 31/12/1921 nên đề nghị này không còn áp dụng."*
2. `Tự sửa hồ sơ` — opens §7.7's person edit form pre-filled with the **proposed**
   values (they are already in PATCH body shape, which is exactly why the contract keeps
   them unwrapped), so the reviewer can merge by hand. On save, returns here with
   `Từ chối` pre-filled *"Đã sửa trực tiếp theo đề nghị này."*

**There is deliberately no force-approve, and the UI must not imply one exists.** A
reviewer hunting for it gets one line under the two buttons:
*"Không có cách duyệt đè. Ghi đè thay đổi của người khác là việc phải làm trực tiếp trên
hồ sơ, với giá trị của họ hiển thị trước mặt."*

**Target deleted** (`is_deleted: true`, or `409 change_request.target_deleted`):

> **Người này đã bị xóa khỏi gia phả**
> Không thể duyệt đề nghị cho một hồ sơ đã bị xóa.

`warning-container`. Admin gets `Khôi phục {tên}` (`POST /persons/{id}/restore`) — after
which the banner re-evaluates and, because delete/restore bump `version` without
touching any proposed field, the proposal typically becomes approvable with
`is_stale: true, conflicts: []`. Editors, who cannot restore, get
*"Quản trị dòng họ cần khôi phục người này trước."* Both roles keep `Từ chối`, which has
no target preconditions at all — clearing an unactionable proposal out of the queue must
always be possible.

**Stale but harmless** (`is_stale: true`, `conflicts: []`) — an `info-container` line,
**not** a warning, and `Duyệt` stays primary:

> Hồ sơ đã được sửa ở mục khác kể từ khi có đề nghị này. Duyệt vẫn an toàn — cả hai
> thay đổi đều được giữ.

---

### 7.10 Quản trị dòng họ — admin panel

**Purpose.** The four things a trưởng họ actually does: let relatives in, decide what
they may do, invite the ones who are not here yet, and keep the clan's own record
straight.

**Entry.** `Quản trị` nav item, admin only (hidden, not disabled, for editor and
viewer). Sub-tabs: `Duyệt thành viên` · `Thành viên` · `Lời mời` · `Cài đặt` ·
`Nhật ký`.

**Mobile.** The admin panel is a phone-first surface — approvals happen from a phone
at a family gathering, not at a desk. Tabs scroll horizontally; each tab is a
`CursorList`.

**Desktop.** Sidebar sub-navigation at ≥1024; content max-width 900.

#### 7.10a Duyệt thành viên (pending approvals)

`GET /clans/me/users/pending` → `ApprovalRow` per pending membership, with
`POST …/{user_id}/approve` and `…/reject`.

**Row content, and a blocker.** Approving a membership grants a stranger access to
several hundred living relatives' records. It is an identity decision, and the API did
not, when this spec was written, return an identity: the pending row was
`{id, user_id, role, person_id, created_at}` — no name and no email, and `person_id` is
`null` for exactly the fresh registrant an admin most needs to judge. **A screen that asks
"Duyệt `d95c1ee7-…`?" is not a screen we should ship.** So this spec designed the row the
decision needs and named the gap precisely rather than papering over it. The gap was
closed on 2026-08-02 — see §9-J18 and
[ADR-039](../../decisions/039-clan-user-list-identity-asymmetry.md).

Row, as designed (the gap is now closed, so this is what ships):

```
Nguyễn Văn Hải                          [Xin làm Người xem]
hai.nguyen@gmail.com
Gửi yêu cầu 2 ngày trước
                                    [Từ chối]  [Duyệt]
```

~~Interim rendering, until `full_name`/`email` are added: the row leads with
`Yêu cầu tham gia` and the join date, shows a short id chip, and the primary action is
**not** `Duyệt` but `Xem chi tiết`, which is honest about the admin needing to identify
the person out of band. `Duyệt` appears only where an identity is shown.~~

**No longer needed — the gap is closed** (2026-08-02,
[ADR-039](../../decisions/039-clan-user-list-identity-asymmetry.md)).
`GET /clans/me/users/pending` now returns `display_name` and `email`, so the row above
renders as designed and `Duyệt` is the primary action. Both fields are **nullable**:
render `display_name` when present, otherwise lead with `email`; if a request somehow has
neither, fall back to the interim treatment above for that row only. The interim rendering
is kept struck-through as the record of what shipped before the fields existed.

**Role select.** The requested role is shown as a chip; the admin can change it before
approving via a `Duyệt với quyền…` menu (`Người xem` / `Biên tập viên` / `Quản trị`),
defaulting to what was requested. Approving with a role is two calls (approve, then
`PATCH …/role`) — the UI shows one action and one success.

**States.** *Loading* — 3 row skeletons. *Empty* — `Không có ai đang chờ duyệt.` and a
line pointing to `Lời mời` as the way to bring someone in. *Approving* — that row only
enters loading; the rest stay live. *`409 user.already_approved`* — silently refetch and
show `Người này đã được duyệt.` (another admin got there first — not an error).
*`404 user_not_found`* — row disappears with `Yêu cầu này không còn nữa.`

#### 7.10b Thành viên và vai trò

`GET /clans/me/users`, `PATCH …/{user_id}/role`, `DELETE …/{user_id}`.

Row: member identity (same gap as above), `RoleBadge`, joined date, and a `⋯` with
`Đổi vai trò` and `Xóa khỏi dòng họ`.

**Last-admin protection is the copy problem here.** Two codes, both 403, both meaning
"the clan would be left with no admin". A bare "không thể" is a dead end; the message
must say what to do instead:

- `clan.last_admin_cannot_demote` → *"Đây là quản trị duy nhất của dòng họ. Hãy bổ nhiệm
  thêm một quản trị khác trước khi hạ quyền người này."* with `Bổ nhiệm quản trị` opening
  the member picker.
- `clan.last_admin_cannot_remove` → same shape, *"…trước khi xóa người này khỏi dòng
  họ."*

Both are **predictable**, so the UI predicts them: when the clan has exactly one approved
admin, that admin's row shows no `Đổi vai trò`/`Xóa` at all, plus one quiet line
*"Dòng họ cần luôn có ít nhất một quản trị."* The 403 handling above remains as the
race-condition backstop (two admins demoting each other simultaneously).

- `clan.cannot_remove_self` → the admin's own row never carries `Xóa khỏi dòng họ`, for
  any admin count. **There is no "Rời dòng họ" action anywhere in the product**, because
  there is no endpoint for one — see §9-J19.
- `clan.role_changed_concurrently` (409) → *"Vai trò vừa được người khác thay đổi."* +
  refetch the row and show the current role; do not retry blindly.
- `invalid_role` (422) → unreachable from a select; if seen, generic error.

**Destructive confirmation.** `Xóa khỏi dòng họ` always confirms, names the person, and
states the consequence in plain Vietnamese: *"Người này sẽ mất quyền xem gia phả dòng
họ. Dữ liệu gia phả không bị xóa."*

#### 7.10c Lời mời

`POST/GET/DELETE /clans/{clan_id}/invitations`. Admin only.

**Create.** Sheet/dialog: `Email` + `Vai trò` segmented (`Người xem` default, per the
API). On 201 the response carries the raw `token` and `accept_path`, so success is a
**one-time link reveal**, not a toast:

> **Đã tạo lời mời cho hai.nguyen@gmail.com**
> Gửi liên kết này cho người được mời. Liên kết có hiệu lực **7 ngày**.
> `https://…/invitations/{token}/accept`   [Sao chép liên kết]
> Chỉ người đăng nhập bằng đúng địa chỉ email trên mới dùng được liên kết này.

The token is a secret: revealed once, never rendered in the list, never in a screenshot-
friendly place, and the copy says what protects it (email binding) so an admin who
forwards it to the wrong person understands the failure mode.

**List.** Plain array, **not** cursor-paginated and with no server-side filters — so the
list is client-filtered (`Đang chờ` / `Đã nhận` / `Hết hạn` / `Đã thu hồi`) and
virtualized above ~200 rows.

**Expiry must be computed client-side.** A timed-out invitation keeps `status:
"pending"` until the next create for that email lazily flips it — there is no sweep. So
the row derives its own state from `expires_at`:

```
hai.nguyen@gmail.com            Người xem
Hết hạn 3 ngày trước                        [Mời lại]
```

`Mời lại` re-posts the same email+role; the backend expires the stale row and issues a
fresh token, so this action reliably succeeds and re-opens the link reveal. A row whose
`status` says `pending` but whose `expires_at` has passed must **never** be shown as
`Đang chờ` — that would have an admin waiting on a dead link. See §9-J20.

**Errors.** `invitation.pending_exists` (409) → not an error state: show the existing
live invitation inline with `Sao chép liên kết` / `Thu hồi`, headed *"Đã có lời mời đang
chờ cho địa chỉ này."* `invitation.not_pending`, `invitation.expired` → refetch the list.

**Accept, from the invitee's side.** `POST /invitations/{token}/accept` works for a
user who is authenticated but not yet approved anywhere, so the accept landing is
reachable from the pending screen (§7.2a). States: success → `Bạn đã tham gia dòng họ
{tên}` and route in; `invitation.email_mismatch` (403) → *"Lời mời này dành cho một địa
chỉ email khác. Xin đăng nhập bằng địa chỉ đã được mời."* with `Đăng nhập bằng tài khoản
khác`; `invitation.expired` (409) → *"Lời mời đã hết hạn. Xin liên hệ quản trị dòng họ để
được mời lại."*; `invitation.already_member` (409) → not an error, route straight into
the clan; `429 rate_limited` → countdown per §3.6.

#### 7.10d Cài đặt dòng họ

`GET /clans/me`, `PATCH /clans/me`, plus `PUT /clans/me/founder`.

Fields: `Tên dòng họ`, `Mã dòng họ` (slug, with a warning that existing invite links and
join codes keep working but the code people quote will change), `Mô tả`, `Nguồn gốc`
(`origin_place`), `Năm thành lập`, `Câu đối / phương châm` (`motto`), `Nhà thờ họ`
(`ancestral_hall_location`), `Tộc ước` (`clan_rules`, long text).

**Thủy tổ** gets its own block, not a form field, because it is a designation and not an
attribute: current founder as a person card, `Đổi thủy tổ` opening the searchable person
picker from §7.4b, and the confirmation naming both people when swapping:
*"Đặt **{tên mới}** làm thủy tổ thay cho **{tên cũ}**?"* Re-designating the current
founder is a harmless no-op and the UI simply closes. `409 conflict` (lost the unique-
index race) → *"Có người vừa đổi thủy tổ. Xin tải lại và thử lại."*

**What this screen must not contain.** The `clan_settings` table (`allow_public_tree`,
`privacy_level`, `tree_display_mode`, `max_upload_size_mb`, `notification_defaults`) is
largely inert — nothing enforces those knobs today, and `max_upload_size_mb`'s default
of 10 contradicts the domain's real 50 MB limit. **No toggle for an unenforced setting
ships**, especially not a privacy toggle: a `Cho phép xem công khai` switch that does
nothing is the most dangerous control we could draw. Filed in §9-J21.

#### 7.10e Nhật ký hoạt động

Clan audit log, admin only. `AuditRow`: actor, action (server-localised — `user.approve`,
`user.change_role` with `old_value`→`new_value`, `person.update`,
`change_request.submit`/`.approve`, `claim.approve`, `clan.update`, …), target, and an
absolute timestamp with a relative one beneath.

Filter chips by area (`Thành viên` / `Nhân khẩu` / `Đề nghị sửa` / `Nhận thân` /
`Dòng họ`). Cursor-paginated. Empty: `Chưa có hoạt động nào được ghi.`

This screen exists mostly for one question — *"ai đã sửa cụ tổ nhà tôi?"* — so a row for
a person edit links straight to that person's profile.

---

### 7.11 Nhận thân — identity claims

**Purpose.** Let a living member say *"bản ghi này chính là tôi"* and have an admin
confirm it. This is what connects a login to a place in the tree, and it is the one flow
where the product touches a person's own identity rather than an ancestor's record.

#### 7.11a Gửi yêu cầu nhận thân

**Entry.** `POST /persons/{id}/claim` from a person profile: `Đây là tôi` as a tonal
action in the `⋯` menu (not in the header — it is rare, and the header belongs to
reading). Sheet: the person card, a `requester_note` field
(*"Cho quản trị biết vì sao đây là bạn — ví dụ: tôi là con ông Trần Đình Vinh."*), and
`Gửi yêu cầu`.

**One pending claim per user, globally.** This is a hard unique constraint, so the UI
must not present a button that will 409. While the user has a pending claim, the action
everywhere reads `Bạn đang có một yêu cầu nhận thân chờ duyệt` and links to it. If a
409 `user_already_has_pending_claim` still arrives (raced), the sheet **replaces itself
with the existing claim** rather than showing an error toast.

Other blocking cases, each with its own copy rather than a shared "lỗi":
`user_already_linked_to_person` (409) → *"Tài khoản của bạn đã được gắn với một người
trong gia phả."* + link to that person; `person_already_linked_to_user` (409) →
*"Người này đã được một tài khoản khác nhận."*; `person_not_found` (404) → the person is
soft-deleted or not in this clan.

#### 7.11b Yêu cầu của tôi

`GET /claims` — the user's own claims, statuses `PENDING` / `APPROVED` / `REJECTED` /
`CANCELLED`. Card per claim: person, `requester_note`, status chip, and on a reviewed one
the `reviewer_note` verbatim.

`Hủy yêu cầu` (`DELETE /claims/{id}`, 204) appears **only** on `PENDING` and only for the
owner. Confirmation, because re-submitting means waiting again.

**Rows can change without the user acting.** Approving a claim auto-rejects every other
pending claim on the same person, so a user may find their claim `REJECTED` with no
reviewer note. The empty-note rejected state therefore has its own copy:
*"Người này đã được một thành viên khác nhận thân."* — inferred from state, not invented.

#### 7.11c Hàng đợi nhận thân (reviewer)

`GET /clans/{clan_id}/claims`. **Admin and editor can view; only admin can approve,
reject, unlink or prelink.**

This is the one place in the product where "remove, don't disable" produces a
read-only screen for a role that can otherwise write. An editor sees the queue with no
action buttons and one line at the top:
*"Chỉ quản trị dòng họ mới duyệt được yêu cầu nhận thân."* Removing the whole screen
would be worse — an editor legitimately needs to know who is claiming whom.

Row: requester, claimed person (avatar, name, đời), `requester_note`, age, status chip.
Filters `PENDING` (default) / `APPROVED` / `REJECTED` / `CANCELLED`; cursor-paginated.

**Approve** confirms with both identities named — *"Xác nhận **{người dùng}** chính là
**{tên trong gia phả}**?"* — and the success toast states the side effect the API
performs silently: *"Đã xác nhận. Các yêu cầu nhận thân khác cho người này đã tự động bị
từ chối."* **Reject** takes an optional `reviewer_note`, encouraged for the same reason
as §7.9d.

**Unactionable claims.** `person_has_no_controlling_clan` (403) is a genuine dead end —
the person's origin clan was cleared, so no clan can ever review the claim. The row
renders with no actions and an honest line: *"Hồ sơ này không còn thuộc quyền quản lý của
dòng họ nào nên không xét duyệt được. Xin liên hệ hỗ trợ."* We do not hide it; a hidden
row is a claim the requester waits on forever.

Race codes on approve — `user_already_linked`, `person_already_linked`,
`claim.not_pending` — all resolve to the same behaviour: refetch the row, show its new
state, no error dialog. The wording differs (`…vừa được gắn với người khác` vs
`…đã được xử lý`) because the admin's next move differs.

#### 7.11d Gắn / gỡ thủ công (admin)

`prelink` and `unlink` live in the member detail (§7.10b) rather than the claims queue,
because they are member administration, not review. `Gỡ liên kết` confirms and states
that the gia phả record is untouched. `user_not_in_clan` (403) → *"Hãy mời người này vào
dòng họ trước."* with `Tạo lời mời`.

---

### 7.12 Ảnh và tài liệu

**Purpose.** The clan's photographs, sắc phong, bia mộ rubbings and scanned gia phả
pages — the evidence behind the records.

#### 7.12a Thư viện

`GET /documents` — cursor-paginated, filters `person_id` and `document_type`.

**The list has no URLs.** `GET /documents` returns summaries **without**
`presigned_url`; only `GET /documents/{id}` mints one. A thumbnail grid would therefore
need one detail request per tile, which on 3G is exactly the wrong shape. So the library
is **a list, not a gallery**:

`DocumentTile` renders from the summary alone — a type icon on a tonal ground, `title`
in `title-md`, `document_type` chip, `original_filename`, `file_size_bytes` humanised,
`taken_date` (a **scalar** date, not a `HistoricalDate` — one of the documented
exceptions), and the linked person when `person_id` is set. **The tile is complete and
useful before any image exists**, which is also what satisfies T-16.

Images are fetched lazily, one detail call per tile, only for tiles that scroll into
view and only for image MIME types — and the tile does not resize when the image
arrives (the icon block and the image occupy the same reserved box). On a metered
connection a `Chỉ hiện ảnh khi tôi bấm` preference stops the lazy fetch entirely.

**Desktop ≥1024** may use a 3-up grid, still list-shaped per tile.

Filter chips: `Tất cả` · `Ảnh` · `Giấy tờ` · `Bằng cấp / chứng nhận` · `Âm thanh` ·
`Video` · `Khác`, plus a person filter when arriving from a profile.

**States.** *Loading* — 6 tile skeletons at the real tile height. *Empty* —
`Dòng họ chưa có ảnh hay tài liệu nào.` + `Tải lên tài liệu đầu tiên` (editor+) or an
explanation (viewer). *Empty for a filter* — `Không có tài liệu nào thuộc loại này.` +
`Xóa bộ lọc`. *Image failed / URL expired* — the tile falls back to its icon state with
`Tải lại`; never a broken-image glyph.

#### 7.12b Tải lên

`POST /documents` (multipart), editor+. Web: drag-and-drop zone plus a file picker.
Mobile: `Chụp ảnh` / `Chọn từ thư viện` / `Chọn tệp`.

Form: `Tiêu đề` (required), `Loại tài liệu` (required, segmented), `Người liên quan`
(person picker, optional), `Mô tả`, `Ngày chụp/thu` (plain date — this one is **not** a
`HistoricalDateField`), `Nơi chụp/thu`.

**Limits stated before the failure, not after.** The zone reads
*"Tối đa 50 MB · JPG, PNG, WEBP, HEIC, PDF, MP3, WAV, MP4, MOV"*, and the client checks
size and type before uploading. Server errors are still handled, and note the trap:
`invalid_mime_type`, `file_too_large` and `invalid_document_type` are **400, not 422** —
branch on the code, not the status.

- `file_too_large` (400) → *"Tệp {tên} nặng {n} MB, vượt quá giới hạn {detail.max_bytes}."*
- `invalid_mime_type` (400) → lists `detail.allowed` in human words, not MIME strings.
- `storage_unavailable` (503) → *"Kho lưu trữ tạm thời gián đoạn. Tệp của bạn chưa được
  tải lên."* + `Thử lại`, with the chosen file retained.

**Progress.** Determinate progress per file, cancellable; a failed file in a multi-file
selection does not roll back the successful ones (each is its own request), and the
result panel lists successes and failures separately.

#### 7.12c Chi tiết, ảnh đại diện, xóa và khôi phục

Detail sheet/page from `GET /documents/{id}`: the media (image inline, PDF/audio/video
as a download or native player), all metadata, and actions by role.

**`Đặt làm ảnh đại diện`** (`PATCH /{id}/set-avatar`, editor+) appears only on
`document_type == "photo"` **and** only when `person_id` is set — the two 422s
(`only_photo_can_be_avatar`, `document_not_linked_to_person`) are made unreachable by
hiding the action rather than by explaining a rejection. If the document has no person,
the action is replaced by `Gắn với một người` which opens the picker first.

**Deleting is admin-only** and soft (ADR-019). Confirmation states the recoverable
window honestly: *"Tài liệu sẽ được ẩn khỏi thư viện. Quản trị có thể khôi phục trong
**30 ngày**, sau đó tệp bị xóa vĩnh viễn."*

**Restore has no discovery path, and the UI must not pretend otherwise.** Reads filter
soft-deleted rows out, and there is **no endpoint listing deleted documents**, so
`POST /{id}/restore` is only reachable by an admin who still has the id. The design
does what it can and no more: after a delete, an undo affordance persists in a
session-scoped `Vừa xóa` tray at the bottom of the library (holding ids from this
session only), labelled *"Chỉ hiện trong phiên làm việc này."* There is deliberately no
`Thùng rác` screen, because it could never be complete. See §9-J23.

**Avatar interplay, surfaced.** Soft-deleting a document that is a person's avatar does
not clear `is_avatar`; the avatar keeps working until the blob is purged and then
vanishes silently. So deleting an avatar photo adds a second line to the confirmation:
*"Đây đang là ảnh đại diện của {tên}. Sau 30 ngày ảnh sẽ biến mất khỏi hồ sơ."*

---

### 7.13 Nhắc nhở và thông báo

**Purpose.** Set expectations about the only notification the platform actually sends,
and let a device turn it on or off.

**There is no notifications API.** No inbox, no read/unread, no history, no preferences
endpoint — `notification_log` is server-side only. The only client-facing surface is
FCM device-token registration (`POST`/`DELETE /auth/me/fcm-token`). So this screen is
**not** a notification centre, and:

- **The bell icon is removed from the app bar.** The first round of dashboard mockups
  drew one; a bell that opens nothing, or opens an empty list that can never fill, is a
  promise the product cannot keep. Its slot in the §7.3 app bar is taken by
  `Đề nghị sửa` with a pending count for editor+, which is a real queue. See §9-J24.
- Nothing in the product shows an unread badge.

**Layout** (mobile, under `Tài khoản`; web, under account settings):

1. **`Nhắc ngày giỗ trên thiết bị này`** — a single switch. On → register the FCM token;
   off → `DELETE` it. Per-device, and the copy says so:
   *"Cài đặt này chỉ áp dụng cho thiết bị bạn đang dùng."* When the OS permission is
   denied, the switch is replaced by `Mở cài đặt hệ thống` — a switch that cannot move
   is worse than a link that works.
2. **`Bạn sẽ được nhắc những gì`** — an honest, complete list, because the send rules
   are narrow and a user who expects more will conclude the app is broken:
   > Hệ thống chỉ gửi nhắc cho **sự kiện lặp lại hằng năm có ngày chính xác** — ngày giỗ,
   > sinh nhật, kỷ niệm ngày cưới. Thư nhắc gửi vào **7 giờ sáng**, trước sự kiện đúng số
   > ngày bạn đặt cho từng sự kiện.
   >
   > Hệ thống **không** gửi thông báo khi: có người xin vào dòng họ, có đề nghị sửa mới,
   > yêu cầu nhận thân được duyệt, hoặc sự kiện chỉ diễn ra một lần.
3. **`Thời điểm nhắc`** — read-only explanation that lead time is per event
   (`notify_days_before`, 0–30, default 7), with `Xem danh sách sự kiện` linking to
   §7.8. There is no global default to set, so none is drawn.
4. A line for events that will never notify: *"Sự kiện ghi ngày ước lượng sẽ không được
   nhắc."* — the same fact §7.8 warns about at input time, restated where a user goes
   looking for a missing reminder.

**Tapping a push opens the events list, not the event.** The FCM payload's `data` is
empty — no `event_id`, no `clan_id` — so a deep link is impossible today, and for a
multi-clan user the app cannot even switch to the right clan. The handler therefore
opens `Sự kiện · Sắp tới` in the currently active clan. This is a backend gap, not a
design choice; recorded in §9-J24.

**Two event types are known to send broken text.** Only `death_anniversary`, `birthday`
and `wedding_anniversary` have translations; a recurring `clan_ceremony` or `custom`
event pushes the raw i18n key as its title. Until that is fixed, the event form's
`Lặp lại hằng năm` switch shows an inline note for those two types:
*"Loại sự kiện này hiện chưa có nội dung nhắc hoàn chỉnh."* — better a small
disclosure than a relative receiving `notification.clan_ceremony.title`.

---

### 7.14 Xuất gia phả

**Purpose.** Let an admin take the clan's data out. `GET /exports/clan?format=json|gedcom`,
**admin only**, synchronous.

**Entry.** `Quản trị › Cài đặt › Xuất dữ liệu`, and `Xuất gia phả` on the tree toolbar
for admins. Absent for editor and viewer.

**Layout.** Two format cards, chosen by what the user wants to do, not by file type:

- **`Bản lưu đầy đủ (JSON)`** — *"Toàn bộ dữ liệu dòng họ, kể cả người đã xóa. Dùng để
  lưu trữ hoặc chuyển sang hệ thống khác."*
- **`Chuẩn GEDCOM 5.5.1`** — *"Định dạng gia phả tiêu chuẩn, mở được bằng hầu hết phần
  mềm gia phả. Người đã xóa không có trong tệp này."*

Each card lists honestly what it does and does not contain, because the difference
matters and is invisible after download: GEDCOM drops soft-deleted records entirely and
does not carry nghề nghiệp, tôn giáo or nơi chốn; JSON carries everything including
`is_deleted` rows.

**A confirmation step is obligatory, and it is about PII.** The JSON archive contains
`phone` and `email` for living relatives with no redaction and no opt-out:

> **Tệp này chứa thông tin cá nhân**
> Bản lưu đầy đủ bao gồm **số điện thoại và email** của các thành viên còn sống, và cả
> những người đã bị xóa khỏi gia phả. Xin chỉ lưu ở nơi an toàn và không chia sẻ công
> khai.
> [Hủy] [Tôi hiểu, tải xuống]

**Two more truths the UI must carry**, both consequences of the archive's shape:

- *"Ảnh và tài liệu không nằm trong tệp. Tệp chỉ chứa danh sách kèm liên kết tải, và
  các liên kết này hết hạn sau khoảng **1 giờ**."* — a week-old archive's photo links
  are all dead, and a user who discovers that later will think the export was broken.
- *"Hệ thống chưa hỗ trợ nạp ngược tệp này trở lại."* Export is one-way; no import
  exists.

**States.** *Idle* → *Đang tạo tệp…* — an indeterminate spinner and
*"Xin giữ nguyên màn hình. Dòng họ lớn có thể mất một lúc."* There is no job queue, no
progress percentage and no polling to design, because the request is synchronous;
inventing a progress bar would be a lie. Then the browser/OS download handoff and
`Đã tạo tệp {tên}`.

*Errors.* `503 storage_unavailable` (the manifest presigns go through storage) →
*"Không lấy được liên kết ảnh nên chưa tạo được tệp. Xin thử lại sau ít phút."*
`503 database_unavailable` → transient retry. A dropped connection mid-download →
`Tải lại tệp`. Because it is envelope-exempt, the client must bypass the standard
`{"data"}` unwrap for this one call.

---

### 7.15 Quản trị nền tảng (super admin)

**Purpose.** The platform operator's view across clans. Entirely separate from clan
UX: different nav, no `X-Current-Clan-Id`, and invisible to every clan role including
admin. `403 super_admin_required` means the area is hidden, never greyed.

**This is the one surface designed desktop-first.** It is operated from a desk, its
tables are genuinely tabular, and its audit log needs width. Mobile gets a reduced
read-only version: metrics, clan list and clan detail, but not the audit log, which is
unusable narrow.

#### 7.15a Số liệu nền tảng

`GET /platform/metrics` — headline figures in `display-md` `tabular-nums` over
`label-md` captions. The metric key names are not documented anywhere, so the layout is
specified as *"a responsive row of stat tiles, one per returned key, label-driven"*
rather than a fixed set — a hard-coded grid would break the first time a key is renamed.
Totals are independent counts, so they are safe to show beside a paginated list.

#### 7.15b Danh sách dòng họ

`GET /platform/clans`, cursor-paginated, no server-side search or status filter
documented — so filtering is client-side over the loaded pages and the UI does not draw
a search box that would silently only search what has loaded. Columns: `Dòng họ` (name +
slug), `Trạng thái` (`Hoạt động` / `Tạm ngưng` — text plus tint, never tint alone),
`Thành viên`, `Ngày tạo`.

**Suspend / reactivate** (`POST …/suspend`, `…/reactivate`) is a heavy action with a
heavy confirmation, naming the consequence for real people:

> **Tạm ngưng dòng họ {tên}?**
> Toàn bộ **{n} thành viên** sẽ không xem được gia phả cho tới khi dòng họ được mở lại.
> Dữ liệu không bị xóa.

Idempotency is undocumented, so the UI treats a repeat call as success and refetches
rather than showing an error. **There is no delete** — clans are suspended, never
removed — so no delete affordance exists anywhere.

#### 7.15c Nhật ký toàn nền tảng

`GET /platform/audit-log`, filters `clan_id` and `action`, cursor-paginated.

**This list is newest-first (DESC) — the only DESC list in the entire product.** The
shared `CursorList` appends at the bottom as it pages, which for DESC means paging
*backwards in time*. The component takes an explicit `order` prop and the screen labels
the direction (`Mới nhất trước`) so the behaviour is stated rather than inferred. Any
component that assumed ASC append is wrong here.

The log is retained **indefinitely** by design, so the screen never offers "load all",
never shows a total, and leads with filters rather than data: an unfiltered infinite
list of every action ever taken is not a feature.

Row: timestamp (absolute + relative), `actor_role` chip, `action`, `resource_type` /
`resource_id`, clan, and `ip_address` / `user_agent` in a secondary line. Expanding a
row reveals `old_value` / `new_value`, which are free-form JSONB — so the detail drawer
uses a **generic JSON diff renderer**, monospace, with changed keys highlighted. Not a
typed field list; the shapes vary per action and always will.

**States.** *Empty for a filter* — `Không có hoạt động nào khớp bộ lọc.` *Loading* — row
skeletons. `clan_id` filter accepts a clan picked from §7.15b rather than a typed UUID.

---

## 8. Where web and mobile deliberately diverge

Divergence is a cost; each of these buys something specific.

| # | Divergence | Why |
|---|---|---|
| D1 | **Tree: canvas (web) vs focus navigator (mobile)** | A pan/zoom graph is the right tool at 1440px and the wrong one at 320dp with 200% text. Mobile is built on `GET /tree/focus/{id}` and navigates person-by-person; web renders `GET /tree`. Both render đời, đa thê grouping and stubs identically. |
| D2 | **Sự kiện: calendar grid (web) vs month list (mobile)** | A 7-column grid cannot hold a Vietnamese event title at large text sizes. Mobile groups by month in a list; web shows the grid *and* the list, grid as navigation only. |
| D3 | **Member list: table (web ≥1024) vs rows (mobile)** | The data is genuinely tabular and the desktop viewport supports it. This is the one place a rigid grid is permitted by the mandate. |
| D4 | **Pagination: auto-load + button (mobile) vs button only (web)** | Infinite scroll on desktop breaks keyboard users and hides the footer; on mobile auto-load is expected, but the explicit button stays because it fails often on 3G. |
| D5 | **Hover states exist only on web** | Mobile substitutes pressed states and long-press sheets. No information is ever hover-only on either client (T-10). |
| D6 | **Tooltips: web only** | Mobile uses an info IconButton opening a sheet. |
| D7 | **Date entry: numeric fields (both) + native picker (mobile, exact only)** | The native wheel picker is faster for a 1990 birthday and useless for 1750. Offered only for `exact` precision within the last ~120 years. |
| D8 | **Documents: drag-and-drop (web) vs camera capture (mobile)** | Platform-native capability, same upload contract. |
| D9 | **Overlays: dialog/side panel (web) vs bottom sheet (mobile)** | Same content, same component contract, different presentation. |
| D10 | **Glass surfaces: up to two (web) vs one (mobile)** | Per-frame blur on a five-year-old Android is a real frame-budget cost; mobile spends it only on the bottom nav. |
| D11 | **Change-request review: two-pane (web ≥1280) vs list→detail (mobile)** | A reviewer with a screen should work the queue without navigating; a reviewer with a phone should see one proposal at a time. The `FieldDiff` component is identical in both. |
| D12 | **Platform admin: desktop-first, reduced on mobile** | The only surface in the product that is not phone-first. The cross-clan audit log with `old_value`/`new_value` JSON diffs is unusable narrow, so mobile omits it rather than shipping a cramped version. |
| D13 | **Documents: list-shaped tiles everywhere, 3-up grid on web ≥1024** | Driven by the API, not the viewport: `GET /documents` returns no URLs, so a thumbnail-first gallery would cost one extra request per tile. Both clients render from metadata and fetch images lazily. |

Everything else — tokens, copy, states, validation, error mapping, đời/đa thê/precision
rendering — is identical by construction. If a behaviour differs and is not in this
table, it is a bug.

---

## 9. Judgement calls and open questions

Where the domain and good UI genuinely pulled in different directions.

**J1 — Three primaries in the codebase, and mobile disagrees with itself.**
`web/src/app/globals.css` declares primary `#c41e3a` (lacquer red, also bound to
`--ring`). Mobile declares a green primary **twice, at two different values**:
`mobile/lib/app/theme/colors.dart` says `#4A6741` and
`mobile/lib/core/theme/app_colors.dart` says `#37563B` — and it is the second one that
screens actually render, because `AppColors.primary` is what the widgets import. So
there is no single "mobile green" to reconcile with web; there are two, and the
`ColorScheme` one is dead code. The mobile rebuild (ADR-034) deletes both files, which
is precisely why this document has to state the replacement rather than inherit one.
All three values are defensible and all three are shipped. Rather than pick a winner,
this system **assigns them different jobs**: leaf green is `primary` (interaction —
buttons, links, active nav, selection), and lacquer + gilt become the reserved
`heritage` family (thủy tổ, giỗ, đời badges, ancestral emphasis). This keeps the
"arbor" reading of the design system, keeps Vietnamese ceremonial colour where it means
something, and — practically — stops red from being spent on ordinary buttons so that it
still reads as significant when it marks the thủy tổ. The shipped values shift slightly
for contrast (`#3E5C38`, `#A3182F`); `gilt-decor` keeps `#D4AF37` exactly.

**J2 — No-1px-border vs. accessibility.** The no-line rule and WCAG focus visibility are
in direct conflict. Resolution: **focus rings, error indicators, active tab indicators,
and relationship connectors are not "lines" in the mandate's sense** — they are state
and data, not section separation — and are exempt. Section separation remains
background-step only. The mandate's own high-contrast exception (`outline_variant` at
15%) is additionally extended to table row separation in the desktop member list, where
scanning a wide row without any separator is measurably worse.

**J3 — `generation: null` on a spatial layout.** đời is the tree's vertical axis, so a
node with no đời has no honest position. Guessing (place it under its parent's band) is
forbidden by the domain rules. Dropping it hides a real person. Resolution: on desktop,
null-đời nodes render in a labelled tray below the canvas (`Chưa nối vào thủy tổ`); on
mobile they appear in their parent's child list with a `Đời ?` badge, because the focus
navigator has no đời axis to violate. Both are honest; neither hides anyone.

**J4 — Stubs that claim descendants.** `pedigree_collapse_ref` nodes have empty
`children` but may report `has_more_descendants: true`. An expander that opens to
nothing is worse than no expander, so stubs get **no expand control at all** — only
`Xem ở nhánh chính →`. We deliberately ignore `has_more_descendants` on stubs.

**J5 — Viewers and the change-request feature. RESOLVED 2026-08-02 (ADR-037).** The
original entry, kept below for the record, said the honest design was to remove every
write affordance from a viewer and refuse to draw a `Đề nghị sửa` button with no
endpoint behind it. That gap is now closed: `POST /change-requests` exists, viewers may
propose person corrections field by field, and editors **or** admins review them. §7.9
is the full flow and §3.5's role table now gives a viewer a real primary action.

Three things about the resolution are worth recording, because they were design inputs
rather than consequences:

- **The reviewer pool is editor+, not admin.** An editor can already make the identical
  edit unilaterally, so an admin-only gate would have protected nothing while letting a
  single busy admin stall the whole queue. The UI follows: `Đề nghị sửa` is a top-level
  nav item for editor and admin, not a sub-tab of the admin panel.
- **The proposal form is the edit form.** The contract deliberately keeps `changes` in
  `PATCH /persons/{id}` body shape so one form serves both. §7.7 is reused wholesale
  rather than a parallel "suggestion" form being invented.
- **Refusing to draw the button was the right call and it is now the precedent.** The
  same test applied to the rest of this spec found `Xuất PDF` failing it (§9-J22): a
  control drawn from a permission row with no endpoint. It has been removed.

*Original entry (2026-08-02, superseded):* "Don't show viewers disabled
buttons" is easy; "give viewers a way to contribute" is not, because no
change-request/suggestion endpoint exists (it is on the DB roadmap, not built). The
honest design is: remove all write affordances, state the role once in plain language,
and link to the admin list. We deliberately do **not** ship a "Đề nghị sửa" button that
would go nowhere. **Open question for the backend:** a suggestion/change-request surface
is the correct long-term answer and would change this screen.

**J6 — `stale_write` conflict resolution depth.** The contract asks the client to
re-apply the user's edit onto fresh data. A full three-way merge UI is beyond a
78-year-old on a phone; blind last-write-wins loses another editor's work. Resolution:
**field-level choice, limited to fields that actually differ**, with the default per
field set by whether *this* user touched it. Typically one or two rows, occasionally
none (in which case we resubmit silently with the fresh version, since there is nothing
to resolve). A `Sao chép nội dung của tôi` escape exists for anyone who wants out.

**J7 — Two kinds of lunar date on one screen.** `HistoricalDate.lunar` is verbatim
user-entered text the server never computes, while ADR-018 *does* compute the next lunar
occurrence for recurring events. Showing both as "âm lịch" would make the product look
like it is contradicting itself. They are labelled differently everywhere
(`Âm lịch (ghi trong gia phả)` vs `Giỗ năm nay · … (dương lịch)`), and the UI never
reformats, validates, or converts the stored lunar string.

**J8 — Estimated dates are normal, not warnings.** The strong instinct is to flag
`circa`/`unknown` with warning colour. In a gia phả covering 1750, the *exact* date is
the exception. Precision chips are therefore neutral-toned and purely informational.
Warning colour is reserved for cases where imprecision has a real consequence — the
recurring-event notice in §7.8.

**J9 — The post-login hold.** The login response's `clan_id` is undefined for multi-clan
users and its `has_pending_membership` is always false. Painting the dashboard from it
risks showing one family's name over another family's data. We accept a ~1 second branded
hold while `GET /auth/me` and `GET /me/clans` resolve. In a genealogy product, being
briefly slow beats being briefly wrong.

**J10 — Locale must not come from the profile.** `preferred_locale` always returns `"vi"`
regardless of what was saved. The language switcher reads and writes client storage (and
`PATCH /auth/me` for persistence) and never reflects the profile response, or a user who
picked English would see it silently revert on every login.

**J11 — Avatars must not depend on `avatar_url`.** `persons.avatar_url` is an
undefined client-writable string that will silently expire if a presigned URL is written
into it, and presigned URLs live one hour. Initials avatars are therefore the primary
rendering and photographs are a progressive enhancement layered on top. **Open question
for the backend:** what belongs in `avatar_url` is still undecided.

**J12 — Uppercase and Vietnamese.** The editorial instinct toward tracked-out uppercase
eyebrow labels actively damages Vietnamese legibility at small sizes. Caps is restricted
to short, mark-free words; everywhere else the eyebrow keeps its tracking and drops the
caps.

### Round two — judgement calls from §§7.9–7.15

**J13 — Three values, shown only when the third means something.** The reviewer's diff
(§7.9d) has `base`, `proposed` and `current` for every field, and the obvious design
renders all three every time. On a 360dp phone that is three columns of which one is
usually redundant, because on the common path `current == base`. So `FieldDiff` renders
per merge verdict: two values when nobody touched the field, a deemphasised "already
fixed" line when someone made the same correction, and all three — with `current`
visually dominant — only on a genuine conflict. The information is never withheld; it
is shown when it changes the decision. The risk accepted is that a reviewer cannot see
`base` on the common path; the mitigation is that on the common path `base` *is* the
displayed current value.

**J14 — `is_stale` is not a warning.** The API's own word for "the record moved" is
*stale*, and the instinct is to paint it amber. But `is_stale: true` with
`conflicts: []` is the **normal, harmless, approvable** case — somebody edited a
different field — and ADR-037 chose a loose three-way merge precisely so those
proposals stay applicable. Colouring it as a warning would train reviewers to hesitate
over a non-event, and a queue people hesitate over is a queue that rots. So stale-
without-conflicts is an `info` line with `Duyệt` still primary, and the triage pill
still reads `Sẵn sàng duyệt`. Only `conflicts` and `is_deleted` change the affordance.

**J15 — A rejected suggestion is not an error.** The requester's list (§7.9b) shows
rejections on `surface-container-high` with the reviewer's note, not in `danger`. A
relative who reported a wrong birth date and was told "no" has participated correctly;
red would read as "you did something wrong" and is the single most likely reason they
never report anything again. Red is reserved for states the system considers broken.

**J16 — Promising a notification the platform cannot send.** The natural copy after
submitting a proposal is "chúng tôi sẽ báo cho bạn khi có kết quả". ADR-037 explicitly
defers notification, and §7.13 confirms the only push that exists is the anniversary
cron. So the confirmation says where to *look*, not that we will *tell*. Same reason
there is no `Thu hồi` button on a pending proposal: no endpoint. Both are recorded as
backend follow-ups, not designed around with fiction.

**J17 — One component knows about the write date shape.** Everywhere else in the product
a date is a `HistoricalDate` object rendered by §3.1. Inside `changes` and
`target.conflicts` it is the scalar `birth_date` + `_precision` + `_display` triple —
a deliberate, frozen contract exception so a reviewer's client can feed the payload
straight back into `PATCH /persons/{id}`. Rather than leak that exception across the
review screens, `FieldDiff` is the **only** component that accepts the write shape, and
it adapts to `HistoricalDateDisplay` internally. If a second component ever needs it,
that is the signal the exception has spread too far.

**J18 — An approval queue that cannot show who it is approving.** Both
`GET /clans/me/users/pending` and `GET /clans/me/users` return
`{id, user_id, role, person_id, created_at}` — **no name and no email**. Approving grants
a stranger read access to hundreds of living relatives' records, and it is an identity
decision made against a UUID. `person_id` helps only when the user has already been
linked to a person; for a fresh registrant it is `null`, which is exactly the case an
admin most needs to judge.

Three options were weighed: design as if names existed (dishonest), design against the
UUID (ships a dangerous screen), or design what the decision requires and name the gap.
This spec takes the third: §7.10a specifies the row with `full_name` and `email`, and
until those exist the interim row's primary action is `Xem chi tiết`, not `Duyệt`.

**The backend fix is nearly free, which raises the priority rather than lowering it.**
Verified in `app/api/v1/clans.py` (lines 95–143): `user_profile` is *already* eager-loaded
on both endpoints via the same LEFT JOIN, and `UserProfile` already carries `email` and
`display_name`. The values are in memory and simply not serialised — both handlers build
their dict by hand and omit them. This is two lines per endpoint, not a query change.

*(Corrected during review: an earlier draft of this entry claimed the pending list lacks
`person_id`. It does not — both lists carry it. The missing fields are `email` and
`display_name`, and they are missing from both.)*

**RESOLVED — 2026-08-02, backend shipped.
[ADR-039](../../decisions/039-clan-user-list-identity-asymmetry.md).**

The fix landed, but **not as this entry recommended.** The recommendation above — add both
fields to both endpoints — was written from the shape of the payloads and missed that the
two endpoints have different guards:

| Endpoint | Guard | Shipped |
|---|---|---|
| `GET /clans/me/users/pending` | `RequireAdmin` | `display_name` **and** `email` |
| `GET /clans/me/users` | `RequireViewer` | `display_name` **only** |

`GET /clans/me/users` is readable by **every approved member of the clan**, so putting
`email` there would have published every member's login address clan-wide. That is also the
exposure [ADR-037](../../decisions/037-change-requests-workflow.md) already closed
deliberately: the change-request review surface excludes `phone` and `email` from
`SUBMITTABLE_PERSON_FIELDS` precisely to keep contact PII out of a shared queue.

`email` on the admin-only pending queue is a different case and is justified: the admin is
making an identity decision, already holds approve/reject/role powers over that account, and
the address is the account holder's own registration email — not a genealogy record about a
third party who never consented.

Consequences for §7.10a: the designed row ships as drawn and `Duyệt` is the primary action;
the interim `Xem chi tiết` treatment is retired (kept struck-through there as the record).
Both new fields are nullable — render `display_name`, else `email`, else fall back.

The asymmetry is pinned by
`backend/tests/integration/test_clan_users_identity_fields.py::test_email_is_on_pending_and_never_on_approved`,
which asserts `email` is present on the pending payload and **absent** (not null) on the
approved one — the guard against a future refactor merging the two handlers into one shared
serialiser and quietly leaking email to every viewer. Contract:
[`docs/contracts/rest-clans-api.md` §User list rows](../../contracts/rest-clans-api.md#user-list-rows).

**J19 — There is no way to leave a clan.** `clan.cannot_remove_self` blocks an admin
removing themselves regardless of admin count, and no leave/transfer endpoint exists for
any role. So no `Rời dòng họ` action appears anywhere in the product. A user who wants
out has to ask another admin. This is stated rather than hidden, and flagged as a
product gap: transfer-then-leave is the missing flow.

**J20 — A status field that lies.** An invitation past `expires_at` keeps
`status: "pending"` until the next create for that email lazily flips it; there is no
sweep. Trusting `status` would show an admin `Đang chờ` for a dead link they are waiting
on. So §7.10c derives the row state client-side from `expires_at` and offers `Mời lại`,
which reliably succeeds. The general rule this establishes: **when a server field and a
timestamp disagree, the timestamp wins in the UI.**

**J21 — No switch for an unenforced setting.** `clan_settings` carries
`allow_public_tree`, `privacy_level`, `tree_display_mode` and `max_upload_size_mb`, and
essentially nothing enforces them (`max_upload_size_mb`'s default of 10 even contradicts
the domain's real 50 MB limit). It would be easy to render them as a settings form. A
privacy toggle that does not restrict anything is the most harmful control in this
product — a trưởng họ could set `riêng tư` and reasonably believe the tree is private.
None of them ship until enforcement does.

**J22 — I drew a button with no endpoint, in the same document that refused to.** The
first draft put `Xuất PDF` on the tree toolbar, available to every role, sourced from
the `Export tree as PDF` row in `rbac.md`. That row has no endpoint: PDF export is out
of scope per ADR-020, depends on ADR-005's unbuilt worker and ADR-004's unbuilt Redis,
and would 422 today. It also contradicted the only real export endpoint, which is
admin-only. Removed and replaced with `Xuất gia phả` (§7.14, admin-only, JSON/GEDCOM).
Recorded rather than quietly fixed, because the lesson generalises: **a permission
matrix is not evidence that an endpoint exists.** When PDF export does land it will be
asynchronous — request, job, notify, download — which is a different screen from §7.14,
not a third card on it.

**J23 — An undo that cannot be a trash can.** Documents soft-delete with a 30-day
restore window, but reads filter deleted rows out and there is no endpoint to list them,
so `POST /{id}/restore` is reachable only by someone who still holds the id. A
`Thùng rác` screen would be permanently and invisibly incomplete. §7.12c ships a
session-scoped `Vừa xóa` tray instead, explicitly labelled as session-only. The 30-day
window is still stated in the delete confirmation, because the user should know the file
is recoverable even when this UI cannot recover it. **Open question:** a
`GET /documents?is_deleted=true` filter would turn this into a real screen.

**J24 — Removing the bell.** The first dashboard mockups drew a notification bell. There
is no notifications API at all — no list, no read/unread, no history — and the only push
that exists is a daily anniversary cron whose payload `data` is empty, so a tap cannot
even deep-link. A bell opening a permanently empty inbox is worse than no bell. It is
removed, its app-bar slot goes to the change-request queue (a real queue with a real
count), and §7.13 replaces the notification-settings screen with an honest per-device
switch plus a precise statement of what the platform does and does not send. **Open
questions for the backend:** `data` keys (`event_id`, `clan_id`) so a tap can navigate;
translations for `clan_ceremony` and `custom`, which currently push a raw i18n key as
their title.

### Deferred (not designed here)

Onboarding tour, password-reset landing detail, PDF gia phả book (§9-J22 — deferred
backend-side, and asynchronous when it lands), document import / archive restore (no
endpoint, export is one-way), a devices list for push tokens (no read endpoint), and
change requests for marriages, parent-child edges, events and documents (ADR-037 scoped
v1 to person updates; widening is additive).

---

## Related documents

- `mobile/CLAUDE.md` — Arbor Heritage mandates (binding)
- `docs/architecture/tree-read-model.md` — đời, đa thê, pedigree collapse, thủy tổ
- `docs/architecture/domain-rules.md` — invariants, Vietnamese glossary
- `docs/architecture/rbac.md` — role matrix
- `docs/contracts/README.md` — envelope, `HistoricalDate`
- `docs/contracts/frontend-integration-guide.md` — client states and error handling
- `docs/contracts/error-codes.md` — full error catalogue
- `docs/contracts/rest-change-requests-api.md` + `docs/decisions/037-change-requests-workflow.md`
  — §7.9; the three-way merge and the `target` block
- `docs/contracts/rest-clans-api.md`, `rest-invitations-api.md`, `rest-claims-api.md` — §§7.10–7.11
- `docs/contracts/rest-documents-api.md` (+ ADR-019) — §7.12
- `docs/contracts/push-notifications.md`, `rest-notifications-api.md` — §7.13
- `docs/contracts/rest-exports-api.md` (+ ADR-020) — §7.14
- `docs/contracts/rest-platform-admin-api.md` (+ ADR-030) — §7.15
