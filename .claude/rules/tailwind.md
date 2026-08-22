---
paths:
  - "web/**/*.{ts,tsx,css}"
---

# Tailwind and styling rules (the `web/` app)

Scope: styling in the `web/` service only. Tailwind CSS v4 through `@tailwindcss/postcss`,
Next.js 16 App Router, React 19.

Source: adapted from
[github/awesome-copilot `instructions/nextjs-tailwind.instructions.md`](https://github.com/github/awesome-copilot/blob/main/instructions/nextjs-tailwind.instructions.md).
That guide is generic and short. It assumes a healthy token set, a working dark theme, and
Tailwind v3 config files. None of those three hold here. The differences are listed below.

Companion rules, and who owns what:

| File | Owns |
|---|---|
| `.claude/rules/nextjs.md` | App Router, Server and Client components, route handlers, envelope, caching, testing |
| this file | Tailwind, tokens, dark mode, responsive layout, accessibility, images and fonts |
| `web/CLAUDE.md` | the full architecture and the nine dependency-cruiser rules |
| `mobile/CLAUDE.md` § "UI: Arbor Heritage design system" | the design mandates, for both clients |
| `docs/superpowers/specs/2026-08-02-design-system-and-screens.md` | the full token set, components, and screens |

When this file and the upstream guide disagree, this file wins. When this file and the design
mandates disagree, the mandates win and this file is the bug.

Facts about the repo in this file were checked on 2026-08-13. Re-check one before you trust it.

## 1. Tailwind v4 is configured in CSS, not in JavaScript

- There is no `tailwind.config.js` and no `tailwind.config.ts`. Do not create one.
- `web/postcss.config.mjs` loads `@tailwindcss/postcss`. That is the whole build wiring.
- `web/src/app/globals.css` is the only stylesheet in the app. It is imported once, by
  `web/src/app/layout.tsx`.
- Theme values go in the `@theme` block in `globals.css`. Custom utilities go in `@utility`.
- Do not add a second `.css` file for a component. Use utility classes.

## 2. The semantic colour tokens resolve, and the values are the decided values

Read this before you pick a colour class. Three different things were wrong here, and all
three are now fixed. The history is kept because each fix left a trap behind.

**Fixed on 2026-08-13 by seed S-001.** `globals.css` used to define seventeen semantic colours
in `@theme` as `hsl(var(--x))` while defining those variables in `:root` as **hex strings**, for
example `--border: #e5e7eb`. `hsl()` takes hue, saturation, and lightness, so `hsl(#e5e7eb)` is
not valid CSS and the browser dropped the whole declaration. All seventeen inherited the body
colour instead. `--secondary` and `--secondary-foreground` were never defined at all.

The seventeen now hold literal values in `@theme`, and the duplicate `:root` block is gone.

**A browser probe cannot check this, and S-001's record says it can. Read this before you trust
either.** Tailwind v4 emits an `@theme` variable only when some generated rule references it. A
token that no class in `web/src` uses is therefore **absent** from the built CSS, and
`color: var(--color-destructive)` then falls back to the inherited colour. Measured 2026-08-13 on
`/vi/login`, both `next dev` on `:3210` and a production build: only `border` and `foreground`
return their declared hex, and the other fifteen return `lab(8.11897 0.811279 -12.254)`, which is
the body colour. `border` survives because the `*` rule applies `border-border`, and `foreground`
because an emitted rule sets `accent-color` from it.

That value is the **same** value S-001 recorded as its negative control, so the probe does not
discriminate: "no class asks for it yet" and "the declaration was dropped" look identical. The
table of seventeen computed values in the S-001 record at `docs/SEEDS.md` could not be reproduced
on this tree on 2026-08-13. Treat it as not reproducible rather than as a measurement.

**This is one of three instances of a rule that is written once, elsewhere.** The probe read back a
value the token did not control, so its passing reading and its failing reading were the same. The
rule, with this instance, the `backend` RLS coverage guard, and the mobile `dividerTheme` field
beside it, is `.claude/rules/seeds.md`, section "A test pins an outcome, not a setting". Add
Tailwind-specific evidence here; do not restate the rule here.

Two rules follow, and the second one is the one that costs time:

- **Check a token by reading `globals.css`, not by reading a computed style.** The stylesheet holds
  the value unconditionally. `web/src/app/contrast.test.ts` does this, in the unit gate.
- **To see a token in a browser at all, a source file must use its class first.** Verified
  2026-08-13: with a throwaway file carrying `text-muted-foreground bg-destructive border-input`,
  the production build emitted `--color-muted-foreground:#6e6653`, `--color-destructive:#a32218`,
  and `--color-input:#8a8072`, each with the matching `.class{…var(--color-x)}` rule. So the values
  are correct and on demand, not dead. **Seed S-007 gated this on 2026-08-22**, and the next
  paragraph is what it built.

**The gate is `web/src/app/theme-tokens.test.ts`, and it compiles rather than reads.** It is in the
unit gate, so `pnpm test:unit` fails when a token cannot resolve, and the failing case is named for
the token. Three things about it are worth knowing before you touch it:

- **It generates the class set instead of relying on `web/src`.** One `bg-*`, `font-*`, `rounded-*`,
  or `animate-*` candidate per declared token, handed to Tailwind through `@source inline(...)` with
  `source(none)`. That is what removes the ambiguity in the paragraph above: once every token is
  referenced, absence from the built CSS means the build dropped it and nothing else. Verified
  2026-08-22 by dropping one candidate from the list, at which point `--color-input` vanished from
  the build, exactly as the fifteen dead-looking tokens did in a browser.
- **It judges the value, not the shape of the text.** Every `var()` is substituted against the scope
  and the result must parse as a colour, so both halves of the S-001 defect fail: `hsl(var(--input))`
  with `--input` gone fails on the missing variable, and `hsl(#8a8072)` with `--input` restored fails
  on `hsl()` not taking a hex. A literal that is not a colour, `#ff` or `bananas`, fails too.
- **A new `@theme` namespace stops it rather than slipping past it.** `UTILITY_PREFIX` knows four
  namespaces. Add `--spacing-*` or `--text-*` to `@theme` and the file throws, naming the namespace,
  because a namespace it skips is a namespace nothing gates. Extend the map, do not delete the throw.

Two things it deliberately does not do. It does not judge whether a value is the *right* colour;
`contrast.test.ts` measures the pairs and ADR-041 decides the values. It does not check the two font
tokens' families, which read variables `next/font` creates at runtime: those are allow-listed, and
`e2e/fonts.spec.ts` is what proves they reach a screen.

**These classes work now:** `bg-background`, `text-foreground`, `border-border`, `bg-card`,
`bg-muted`, `text-muted-foreground`, `bg-popover`, `bg-accent`, `bg-secondary`,
`text-destructive`, `bg-destructive`, `ring-ring`, `border-input`, and every `*-foreground`
variant of the seventeen names. So do the primary family `bg-primary`,
`text-primary-foreground`, `bg-primary-container`, `text-primary-container-foreground` and
their `hover:` twins `bg-primary-hover` and `bg-primary-container-hover`; the heritage family
`bg-heritage`, `text-heritage-foreground`, `bg-heritage-container`,
`text-heritage-container-foreground`; `cream-50` to `cream-400`, `gold-100` to `gold-900`,
`font-serif`, `font-sans`, `font-mono`, `rounded-sm`, `rounded-md`, `rounded-lg`, and the three
`animate-*` values. Note that § 5 forbids `rounded-sm` on design grounds even though it resolves.

**Three class names that used to work are gone, and a grep will still find them in old
branches.** Seed S-005 deleted them on 2026-08-14, per ADR-041:

| Gone | Use instead |
|---|---|
| `primary-50` to `primary-900`, the nine-step red ramp | `primary`, `primary-container`, and the two `-hover` twins |
| `bg-cream`, the bare token | `bg-background`. The `cream-50` to `cream-400` **ramp stays** |
| `ring-primary-*` | `ring-ring`, and see the offset rule below |

**Contrast was fixed on 2026-08-13 by seed S-003, and it is now gated.** Three token values moved,
each to the value spec § 2.1 already names for that role:

| Token | Was | Is | Worst ratio, over the four grounds | Spec role |
|---|---|---|---|---|
| `muted-foreground` | `#6b7280` | `#6e6653` | 5.17 | `on-surface-muted` |
| `destructive` | `#ef4444` | `#a32218` | 7.50, both directions | `danger` |
| `input` | `#e5e7eb` | `#8a8072` | 3.53 | none: derived, see below |

The grounds were four when S-003 measured them. **They are three since 2026-08-14**: `card`
`#ffffff`, `background` `#fbf8f1`, and `muted` `#f3f4f6`. `cream` left the set because seed
S-005 deleted the bare token, so `body` and the semantic token now name the same value. The
worst ratios above were measured against the old four and did not move: `background` got
lighter, and a lighter ground raises the ratio for dark text.

Four things to know before you touch these:

- **`destructive` is one digit from `heritage` `#a3182f`.** They are different families on purpose:
  `heritage` is ceremonial, for the thủy tổ marker and giỗ. Do not swap one for the other.
- **`border` stays light at `#e5e7eb`, and that is not an oversight.** The `*` rule in `globals.css`
  applies `border-border` to every element, so darkening it draws a line around everything and
  breaks the no-line rule in § 5. `input` is the token that carries a control's boundary, so `input`
  is the one held to 3:1. Spec § 2.8.1 F reasons the same way. Do not collapse the two values.
- **`input` `#8a8072` is derived, not quoted.** Spec § 2.1 offers no bordered-input value because it
  specifies a filled field instead, `surface-container-low` `#F4EFE4`. Spec § 2.8.1 F allows either
  branch, and S-003 took the darker-border branch as the smaller change. **S-005 did not adopt the
  fill**, so the token stays: ADR-041 decides `primary`, `heritage`, `background`, and `ring`, and
  says nothing about the field. Whether the field becomes filled is still open, and S-035 is the
  seed that would take it.
- **`text-gold-*` is a lint error.** Gold is ornament: `gold-500` measures 2.10:1 on a white card,
  and the ramp does not clear 4.5 for text until `gold-800`. Tailwind v4 generates the text, fill,
  and border utilities from one variable, so the text scale cannot be trimmed on its own. The ban
  lives in `web/eslint.config.mjs` as `no-restricted-syntax`, matching any string literal, so
  `cn('text-gold-500')` is caught too. `bg-gold-*` and `border-gold-*` stay legal. For genuine gold
  text, spec § 2.1 names `gilt` `#8a6a16`. **It did not arrive with S-005**, and the sentence here
  that said it would was wrong: ADR-041 decides four things and the gold family is not one of them.
  No token holds `#8a6a16` today, so there is still no legal way to draw gold text.

**`web/src/app/contrast.test.ts` holds all of it in the unit gate.** It parses the hex values out of
`globals.css` and computes 30 pairs, so a value that drops below AA fails `pnpm test:unit`. Move the
token, never the threshold. It throws rather than skipping when a token is renamed, because a pair
table that silently resolves to nothing passes every assertion.

**Primary is the leaf green, since 2026-08-14.** This is the third fix, and it is the one that
changed what is on screen. ADR-041 decided it and seed S-005 landed it in one change:

- **`primary` is `#3e5c38`.** The red `#c41e3a` is gone from `web/src`. Red did not disappear
  from the palette: it moved to `heritage` `#a3182f`, its own four-token family for the thủy tổ
  marker, giỗ, and ancestral emphasis. `destructive` `#a32218` is a third red and a third job.
  Three reds, three families, one digit apart in two cases. Read the token name, not the swatch.
- **The nine-step ramp was deleted, not recoloured.** Spec § 2.1 publishes no nine-step green, so
  a recolour meant inventing eight values. Four tokens carry every job the thirteen ramp classes
  did: `primary`, `primary-foreground`, `primary-container`, `primary-container-foreground`.
- **Hover is derived, never a second hex — in light.** `--color-primary-hover` is
  `color-mix(in oklab, var(--color-primary) 94%, black)`, which is spec § 4.1 line 582's "fill
  darkened 6%". Tailwind v4 resolves the mix at build time and emits an sRGB fallback beside it.
  `contrast.test.ts` asserts the derivation, because a `color-mix` is not a hex and the pair
  table cannot measure one. **The dark scope names a literal hex instead, on purpose**, and § 3
  holds the measurement that forced it. Do not make the two scopes match.
- **The page ground is one value under one name**, `background` `#fbf8f1`, spec § 2.1's
  `surface`. Two values used to claim the name.
- **`--secondary` and `--secondary-foreground`** had no value at all, so S-001 gave them
  `#7a6248` and `#ffffff` from spec § 2.1's `secondary` row.

**The focus ring is the on-surface colour, and its offset is load-bearing.** `--color-ring` is
`#1d1b16`, not an accent. Measured 2026-08-14: the ring is **2.29:1** drawn straight onto a
filled `primary` button and **16.22:1** against `background`, so `focus:ring-ring` without
`focus:ring-offset-2` is non-compliant under WCAG 1.4.11 whatever the token says. Ship the
offset. `web/src/app/focus-ring.test.ts` fails the unit gate if a `focus:ring-ring` appears
without one; it deliberately ignores a bare `ring-ring`, because a selection indicator is not a
focus ring and needs no offset.
- **The screens are half onto the tokens, and the half that is left is the accessible half.**
  Re-counted 2026-08-14 across `web/src`, excluding `globals.css` and the tests: `bg-background`
  in **6** files and `ring-ring` in **10**, both arriving with S-005. Still **zero** for
  `muted-foreground`, `bg-muted`, `border-input`, and every `*-destructive` class. Forms draw
  their own boundary with `border-gray-300` in **10** files, which measures 1.47:1 on white and
  fails WCAG 1.4.11. So S-003 still changed no pixel, and S-035 is still the seed that moves the
  forms.

Rules that follow from this:

- **Do not add a new token in the `hsl(var(--x))` form. Put the value straight in `@theme`.**
  This is the defect that cost seventeen tokens. Since 2026-08-22 the unit gate catches it, in
  `theme-tokens.test.ts`, so you will find out in `pnpm test:unit` rather than on a screen.
- **Use the semantic token, not Tailwind's own palette**, for example `text-muted-foreground`
  rather than `text-gray-500`. Since 2026-08-21 this has a second and harder reason than contrast:
  a palette colour has no dark value, so `text-gray-500` is a screen that does not follow the
  theme. See § 3. On a form boundary use `border-input`; it is the only value in the file that
  clears 3:1.
- A resolving token is not an approved colour. Check the value against spec § 2.1 before you
  build a screen on it. Since ADR-041, `primary`, `heritage`, `background`, and `ring` are
  decided, so read the ADR rather than the spec for those four: where the two differ, the ADR is
  the record and the spec is its input.
- **Do not read a colour off a mid-transition element.** A button carrying `transition-colors`
  returns an interpolated value from `getComputedStyle` for the length of the transition, and
  Chrome serializes an interpolation as `oklab(...)` rather than `rgb(...)`. Measured while
  closing S-005: read immediately after `.hover()`, the hovered fill came back as the *original*
  colour spelled in oklab, which reads exactly like "the hover class did nothing". Wait for the
  transition, then read.

## 3. Dark mode is built, on one mechanism, and most screens do not follow it yet

**Rewritten 2026-08-21 by seed S-006.** This section used to say dark mode was declared and not
built. It is built. What is *not* done is the screens, and that distinction is the whole of this
section.

**The mechanism is `prefers-color-scheme`, and it is the only one.** ADR-045 decided it.
`globals.css` holds one unlayered `@media (prefers-color-scheme: dark)` block with a `:root` rule
overriding twenty-five `--color-*` tokens: the seventeen semantic names, the `primary` family, and
the `heritage` family. The `@custom-variant dark (&:is(.dark *))` that used to sit on line 3 is
**deleted**, so the Tailwind v4 default `dark:` variant applies, and the default is the media
query. Palette and variant now switch on one signal.

- **You may write `dark:` classes now**, and they will work. There were **zero** in `web/src` on
  2026-08-21, so you would be the first; prefer overriding a token to writing one, because a token
  flips every screen at once.
- **Do not add a `.dark` class or a `data-theme` attribute.** `contrast.test.ts` fails if either
  string appears in `globals.css`. Both are inert without a theme switch, which does not exist.
  A switch is a real want and it revisits ADR-045, rather than adding a fourth mechanism.
- **Never branch on the theme in TypeScript.** Unchanged, and now enforced by there being nothing
  to branch on: no class, no attribute, nothing a component can read.
- **Do not move the dark block into a layer.** `@theme` emits into `@layer theme`, and unlayered
  CSS beats every layer. Inside `@layer base` the block loses and the app stays light **with no
  error anywhere**. `web/e2e/dark-theme.spec.ts` is what catches it, because a stylesheet shows
  you both declarations and not which one won.

**The palette is correct and the screens are not. Counted 2026-08-21 across `web/src`: 393
hardcoded palette utilities in 41 files** — `text-gray-*` 187, `border-gray-*` 82, `bg-gray-*` 33,
`divide-gray-*` 2, plus 89 in the red, amber, blue, green, purple, rose, pink, and orange
families. A palette colour has no dark value, so none of them flips. **Seed S-038 owns moving
them.** Do not report a dark screenshot full of light grey boxes as a new defect; it is this.

**The dark hover fill names a literal hex where the light one names the token, and that asymmetry
must not be "fixed".** Lightning CSS resolves a `var()` inside a `color-mix` against the top-level
`:root`, not the block the declaration sits in, when it emits the pre-`color-mix()` sRGB fallback.
Measured on a production build 2026-08-21: with the token, the dark fallback came out `#4d6948`,
the *light* primary lightened, and the label on it measures **2.57:1**. With the literal, the
build resolves the mix outright to `#aac8a0` and the label measures 8.60:1. `contrast.test.ts`
fails if the literal stops matching its token, so the duplication is gated rather than trusted.

**The backoffice aside stopped being hand-built, per ADR-046 and seed S-061 (2026-08-22).**
`components/backoffice/BackofficeSidebar.tsx:30` used to be `bg-gray-950` `#030712`, a palette
colour that cannot flip, with a `primary-container` brand mark on top of it because `primary`
only cleared 2.68:1 on that ground. Both are gone. The aside now takes `bg-muted text-foreground`,
the same `muted` ground `contrast.test.ts` already measures at `:168`, so every ink the rail
composes is a pair the gate already runs, twice, once per scheme — no new row was needed. On
`muted` the order swaps: measured 2026-08-22, `primary` is 6.83:1 in light and 8.20:1 in dark,
`primary-container` is 1.20:1 and 1.50:1, so the mark moved back to `primary`. The two
`border-gray-800` hairlines are deleted outright rather than re-coloured, per the no-line rule in
§ 5 below; the sections separate with margin instead. `layout.tsx:30` and `:32` moved from
`bg-gray-900`/`bg-gray-50` to `bg-background` in the same change, because the two files have to
move together or the rail and the page go the same darkness in dark mode. `web/CLAUDE.md`'s own
account of S-061, and `docs/decisions/046-backoffice-aside-is-a-surface-step-not-an-inverted-region.md`,
carry the full measurement table and the one open question this did not close: the rail-to-content
step in light mode is a thin 1.04:1, because light `muted` is a cool grey where spec § 2.1
publishes a warm one, and this seed did not move `muted` to fix that.

**Both themes are gated, in two places.** `web/src/app/contrast.test.ts` runs its whole pair table
twice, once per scope, and it parses the stylesheet with comments stripped so that `globals.css`
can name the rejected mechanisms in prose without tripping the mechanism cases. Worst dark ratios
on 2026-08-21: 6.07:1 against the 4.5 floor and 6.07:1 against the 3 floor, zero failures.
`web/e2e/dark-theme.spec.ts` measures `body` in Chromium under both emulated schemes on
`/vi/login` and `/vi/register`.

**One trap from writing those gates, worth more than the rest of this section.** A file-wide
`--color-x: #hex` match over `globals.css` now reads the dark values, because they come later in
the file. S-006 planted exactly that and **all 156 cases still passed**: each palette is
internally consistent, so grading dark against dark clears AA just as light against light does.
A parser that reads the wrong theme does not fail, it agrees with you. Scope any read of that file
to a block, and keep the `two different palettes` case that catches it.

## 4. Where styling code goes

- `cn` (`web/src/lib/utils/cn.ts`) merges classes with `clsx` plus `tailwind-merge`. Use it
  for every conditional class. Do not hand-build class strings with template literals.
  `src/lib/utils/` is fine to use. `src/lib/api/` and `src/lib/hooks/` are the frozen trees.
- Reusable primitives live in `web/src/components/ui/`. It holds exactly one file today,
  `skeleton.tsx`. Feature components live in `web/src/components/<feature>/`.
- `class-variance-authority` is installed and used by no file. All twelve `@radix-ui/*`
  packages are installed and imported by no file under `src`. If you use either, you are the
  first, so set the pattern carefully and say so in the pull request.
- There is no `src/shared/ui/`. Moving the primitives there is an open decision, per
  `web/CLAUDE.md`. Do not move them as part of a feature.

## 5. Obey the Arbor Heritage mandates

These come from `mobile/CLAUDE.md` § "UI: Arbor Heritage design system" and bind the web app
too. The repo-root `CLAUDE.md` names them as mandatory.

- **No-line rule.** No 1px solid borders to separate sections. Express a boundary with a
  background shift instead.
- **Shape.** Soft and rounded. `rounded-full` for primary buttons, `2rem` for tree nodes.
  Never `rounded-sm` and never `rounded-none`.
- **Depth.** No rigid drop shadows. Use ambient depth, roughly a 32px blur at 6% opacity.
  Floating cards and nav bars use 80% opacity plus a 20px backdrop blur.
- **Colour.** Never `#000000`. Primary text is `#1d1b16`.
- **Layout.** No rigid grid unless the data is genuinely tabular.
- **Text scale.** Every layout must survive 200% text scale.

## 6. Responsive layout

The upstream guide says "responsive design patterns" and "container queries". Here is what
this repo actually specifies and actually does.

Spec § 6 defines the web layout: content max-width 1200px, centred.

| Width | Layout |
|---|---|
| < 640 | single column, drawer nav |
| 640 to 1023 | single column, wider gutters, drawer nav |
| 1024 to 1279 | sidebar 264px plus one content column |
| >= 1280 | sidebar 264px plus content; a detail screen may split into main `1fr` and aside 360px |

- Design mobile first. Write the base classes for the narrow case, then add `md:` and `lg:`.
- Responsive coverage is thin today: 4 `sm:`, 8 `md:`, 3 `lg:`, and no `xl:` or `2xl:` uses
  across `web/src`. Treat a new screen as needing responsive work, not as inheriting it.
- Container queries are used nowhere in `web/src`. Tailwind v4 ships them. You may use
  `@container` for a component that must adapt to its own box, but do not convert existing
  breakpoint code to container queries as a drive-by change.

## 7. Accessibility is a release gate, not a polish step

Spec § 5 lists eighteen testable requirements, `T-01` to `T-18`. Read them before you build a
screen. The ones that most often get missed:

- `T-03` touch targets: at least 44 by 44 px for a pointer, 48 by 48 dp on mobile.
- `T-04` 200% text scale: no clipped glyph, no overlap, and no horizontal page scroll at
  320dp width.
- `T-06` colour is never the only channel. Every state needs text or an icon as well.
- `T-05` no fixed height on any container that holds user text or a translated string.
  Vietnamese with full diacritics is taller than English.
- `T-09` zero layout shift: a skeleton must match the final geometry.

`web/src` contains 2 `aria-*` attributes in total. There is no accessibility floor to inherit.

**Three of the eighteen have a test. `T-01`, `T-02`, and `T-04`.**

`T-01` text contrast and `T-02` non-text contrast are held by `web/src/app/contrast.test.ts`, added
2026-08-13 by seed S-003, in the unit gate. `T-01`'s own pass criteria asks for exactly that shape:
"a token-pair audit script over the approved pairs list, not spot-checking screenshots". The pairs
list is the `CASES` table in that file. **Add a row when you add a token**, because the gate can only
check the pairs somebody wrote down. Two limits worth knowing: it checks token **pairs**, so a screen
that puts `text-gray-500` on `bg-cream` is invisible to it, and it reads the stylesheet rather than a
rendered page, for the reason § 2 gives.

**`T-04` was the first of the eighteen to get a test, and the test found a real defect.**
`web/e2e/text-scale.spec.ts`, added 2026-08-13 by seed S-034, sets the viewport to 320 px, injects
`:root { font-size: 32px }`, and asserts that `document.documentElement.scrollWidth` equals
`clientWidth` on `/vi/login` and `/vi/register`. Four traps came out of writing it, and all four cost
time:

1. **A long unbreakable word scrolls the whole page, and no gate sees it.** `FamilyRoots` in a
   `max-w-sm` column measured 350 px against a 256 px box, so both public pages scrolled sideways.
   Type-check, lint, and the component suite all pass over it: jsdom has no layout engine, so only a
   real browser measures a box. Copy the e2e shape when you add a screen, do not assume the CSS is
   right because it reads right.
2. **`Family<wbr />Roots` is the fix, and it looks like a typo.** `<wbr>` is a break *opportunity*:
   the browser uses it only when the line does not fit, so the mark stays on one line at every normal
   size, and `textContent` stays one word, so nothing a screen reader announces changes. Both
   wordmarks carry a comment saying it is load-bearing. Do not delete it as noise, and do not replace
   it with `break-words`, which would break inside a half.
3. **Shrinking the type does not reach, so do not reach for it first.** `px-4` doubles with the root
   font size too, which is why the column is 256 px. Fitting 350 px into it needs `text-xl` or
   smaller, three steps down from `text-3xl`. Spending a line usually costs less than shrinking the
   thing being read. A `clamp()` on `vw` is worse than either: `vw` does not grow with text zoom, so
   it passes the measurement by opting the text out of scaling.
4. **Do not set the scale with `documentElement.style.fontSize` in a Playwright test.** `<html>` is
   React-owned, so writing to it before hydration finishes prints a hydration attribute mismatch in
   the dev-server log — noise the test itself produces, which reads like an app defect. Use
   `page.addStyleTag` with a `:root` rule. `e2e/fonts.spec.ts` still uses the inline form and still
   emits that warning.

**A fifth trap, found by seed S-042 (2026-08-22): the same defect shape hides behind an env-var
guard, and a placeholder meant to fix the gate can make it invisible instead.**
`SupabaseSetupNotice.tsx` renders a banner only when `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` are both missing, and its hint text names both literally, in
every locale (`grep -n missing_supabase_config_hint web/messages/*.json`) — real env var names,
not translatable copy. Both are one unbreakable word: no space, no hyphen, nothing but
underscores. Measured 2026-08-22 at 320 px and 200% root font size, with the banner forced to
render: page `scrollWidth` 569 against `clientWidth` 320, the hint paragraph itself 504 against
190. Same shape as trap 1 above, one step removed: S-041 had just made the e2e run supply
placeholder Supabase values so the *other* four cases stop measuring the runner's filesystem
(`web/CLAUDE.md`'s account of that seed), which as a side effect made this banner **stop
rendering** in every e2e run — the defect did not go away, it went where no gate could see it.

1. **Fixed the same way as trap 2, generalised to a translated, multi-token string.** Splitting
   the *whole* translated hint on `_` and re-joining with `_<wbr />` (`withBreakOpportunities` in
   `SupabaseSetupNotice.tsx`) gives a break opportunity after every underscore in both tokens,
   with no `t.rich` markup and no hardcoded copy of either variable name in any of the four
   locale files — safe only because no locale's surrounding prose contains an underscore of its
   own (checked 2026-08-22), so nothing outside the two tokens is touched.
2. **Measuring the fix needs the banner to render on purpose, and one dev-server process cannot
   answer both ways at once.** `NEXT_PUBLIC_*` values are inlined when a Next.js server process
   starts, not re-read per request, so the placeholder server S-041 built and the banner's own
   server need to be two different processes. `web/playwright.config.ts`'s `webServer` is an
   array now: a second entry boots a dedicated `next dev` with both variables forced to `''`
   (not merely omitted — an unset shell variable would leak through), for
   `e2e/supabase-banner.spec.ts` alone.
3. **A second `next dev` on the same `distDir` refuses to start, silently pointing at the wrong
   fix otherwise.** Next.js 16's `experimental.lockDistDir` (on by default) takes a lock at
   `<distDir>/lock` and a second process sharing it prints "Another next dev server is already
   running" and exits 1 — verified 2026-08-22 by running two `next dev` processes on different
   ports against the same checkout. `web/next.config.ts` reads `PLAYWRIGHT_SECOND_DIST_DIR` so
   the banner's dedicated server gets its own build directory; every other invocation
   (`pnpm dev`, `pnpm build`, the primary e2e server) leaves the env var unset and keeps using
   `.next`.
4. **Next.js patches `tsconfig.json`'s `include` array the first time a new `distDir` runs**,
   appending `<distDir>/types/**/*.ts` and `<distDir>/dev/types/**/*.ts` unprompted. That is a
   real, permanent addition once a second `distDir` exists in the project — not build noise to
   discard — so it is committed alongside the config that introduces the second `distDir`,
   rather than left to reappear as an uncommitted diff after the next person's gate run.

**One on-screen wordmark is still one unbreakable word**, the literal string `FamilyRoots` at
`components/backoffice/BackofficeSidebar.tsx:49` (moved from `:44` by seed S-061's 2026-08-22
conversion, which renumbered the whole file — re-grep before trusting this line too). It sits
behind a Supabase session, so nobody has measured it at 320 px and 200% scale. It still carries
`text-xs font-semibold`, unchanged by S-061 (ADR-046's per-line table names no change for this
line); what moved is the line above it, the translated `rail_label`, from `text-[10px]
text-gray-400` to `text-xs text-foreground` and first in reading order, per the ADR's own table.
So it is still no more likely to overflow than it was, but "no more likely" is not a measurement.
Treat it as unverified, not as fixed.

**S-034 named a third wordmark that does not exist, and its line number for the second one was one
place off.** The seed's `Out of scope` line cites `components/layout/Sidebar.tsx:65` as a
`FamilyRoots` wordmark and `BackofficeSidebar.tsx:33` as the other. Read on 2026-08-13:
`Sidebar.tsx:65` holds `Gia Phả`, not `FamilyRoots`, and `grep -rn FamilyRoots src/` finds no match
in that file at all; the backoffice mark is on line 35. Nothing in the fix rested on either number,
which is precisely why nobody would have caught them. Grep for the string before you trust a cited
line here.

**Fixed by seed S-022, and the trap for next time it is touched.** `web/src/app/layout.tsx`
used to hardcode `<html lang="en">`, and `web/src/app/[locale]/layout.tsx` rendered a `<div>`
instead of the document element — that broke `T-12`. The obvious-looking fix is to move
`<html>`/`<body>` down into `app/[locale]/layout.tsx` so it can read the route's own locale
directly. **That fix does not compile.** `web/src/app/page.tsx` (the bare `/` route) and
`web/src/app/api/*` sit outside the `[locale]` segment but are still siblings of it under
`app/`, so they share the same, single, required root layout — Next.js only allows more than
one root layout when every top-level entry sits inside its own route group, and turning
`page.tsx` into one is a bigger restructure than this fix needs. Nesting a second `<html>`
inside `app/[locale]/layout.tsx` while `app/layout.tsx` still renders one is also just invalid:
React does not allow `<html>` inside `<body>`.

The fix that shipped: `app/layout.tsx` stays the one root layout and calls next-intl's
`getLocale()` (from `next-intl/server`) instead of hardcoding `"en"`. `getLocale()` reads a
request header the intl middleware already set from the URL prefix, so it resolves correctly
for `/vi/login` and `/en/login` even though it is called one layout above `[locale]` — locale
resolution in next-intl is scoped to the request, not to which component in the tree asks for
it. `app/[locale]/layout.tsx` dropped its `<div className="antialiased">` wrapper entirely
(`globals.css`'s `body { @apply ... antialiased }` already carries that class on the real
document element, so the div was a second, dead copy) and returns a `<>` fragment instead.
`web/e2e/smoke.spec.ts:44` is a plain `test()` now, covering both `/vi/login` and `/en/login`.

## 8. Images and fonts

**Images.** `next/image` is configured but unused.

- `web/next.config.ts` already allows `*.supabase.co` and `*.supabase.in` under
  `/storage/v1/object/**` in `images.remotePatterns`.
- No file in `web/src` imports `next/image`. One raw `<img>` exists, in
  `web/src/components/members/MemberAvatar.tsx:56`, with an eslint-disable comment above it.
- Use `next/image` for new images. Add a hostname to `remotePatterns` when the source is new.
- `T-16` says every screen must stay usable with all images blocked. An avatar falls back to
  initials. Reserve the space so nothing moves.

**Fonts.** Fixed on 2026-08-13 by seed S-002. The two mandated families now load and reach
the screen. Read the five traps below before you touch any of it, because four of them cost
this app both of its fonts once already.

What the setup is now:

- **The mandate is `Plus Jakarta Sans` for headings and `Manrope` for body.** Both load
  through `next/font/local` in `web/src/app/layout.tsx`, which is the layout that renders
  `<html>`, and both variables are set on that element.
- `globals.css` reads them through `@theme`: `--font-serif` carries the heading face and
  `--font-sans` carries the body face. The `body` and `h1`-to-`h6` rules in `@layer base`
  apply `font-sans` and `font-serif`, so no rule names a family.
- Measured against a production build on 2026-08-13, Chromium, `/vi/login`: computed
  `font-family` is `manrope, "manrope Fallback", system-ui, sans-serif` on `body` and
  `plusJakartaSans, …` on the `h1`, both faces report `status: loaded` and a `200 800` weight
  range. `web/e2e/fonts.spec.ts` re-runs that reading in the e2e gate.

The five traps:

1. **Never write a literal family name.** `next/font` generates the family name, so a literal
   name matches nothing: the file downloads and the browser then paints a system fallback.
   That was the defect, and it is invisible to type-check, lint, and every unit test. Read the
   face through `--font-sans` or `--font-serif`.
2. **The generated name follows the JavaScript constant**, not the file and not the family in
   the font. `const manrope = localFont(…)` produces the family `manrope`. So never assert on
   a family string; match case-insensitively on the readable part, as `fonts.spec.ts` does.
3. **Both files are variable fonts with a `wght` axis from 200 to 800, so declare
   `weight: '200 800'`.** Manrope's default instance is ExtraLight, and its name table reads
   `Manrope ExtraLight`. A face declared without the range renders body text far too thin.
4. **`--font-serif` carries a sans face.** Plus Jakarta Sans is not a serif. The token name is
   what every `font-serif` class in `web/src` already spells, and renaming it is a separate
   change. Do not "fix" the token by pointing it at a serif.
5. **The utilities layer beats the base layer.** A heading that carries `font-serif` takes the
   token directly, so it renders correctly even when the `h1`-to-`h6` base rule names a dead
   font. Any check of the base rule has to use a heading with no class. `fonts.spec.ts` covers
   both paths for that reason.

Two more facts worth knowing before you change the files:

- **The `.ttf` files are copies, and a test holds them to the originals.**
  `web/src/app/fonts/PlusJakartaSans.ttf` and `Manrope.ttf` are byte-for-byte copies of the
  ones the Flutter app ships at `mobile/assets/fonts/`, so the two clients render the same
  shapes. `web/src/app/fonts/fonts-in-sync-with-mobile.test.ts` compares SHA-256 hashes in the
  unit gate. If it fails, copy the changed file rather than editing either copy. `OFL.txt`
  ships beside them because the licence requires it.
- **The build emits both files whole: 176 KB plus 165 KB, measured 2026-08-13** in
  `.next/static/media/`. `next/font/local` does not subset or convert, so a Vietnamese page
  carries 341 KB of font. Subsetting to woff2 would cut most of it and is an `Owed` row in
  `docs/SEEDS.md`, not a drive-by change: a derived file cannot be hash-compared to the mobile
  original, so the drift test above needs a different mechanism first.
- `web/src/app/fonts/` also holds `GeistVF.woff` and `GeistMonoVF.woff`. No file references
  them. They are leftovers from the project template. Do not wire them up.
- Vietnamese coverage is not a worry with these two files. Checked 2026-08-13 with
  `fontTools`: 721 glyphs in Plus Jakarta Sans, 678 in Manrope, and neither is missing any
  character of `ạảãăắằẳẵặâấầẩẫậđêếềểễệôốồổỗộơớờởỡợưứừửữựỳỵỷỹý` or its uppercase forms.

## 9. How to write the classes

- Order classes as `prettier-plugin-tailwindcss` would. It is configured in `web/.prettierrc`,
  but you must not run `pnpm format`: `web/CLAUDE.md` records 112 files with pre-existing
  Prettier drift, so a format run buries the real diff. Keep new class lists tidy by hand.
- Arbitrary values are common today, mostly font sizes such as `text-[10px]` and
  `text-[11px]`. Spec § 2.3 defines a real type scale, and it is not implemented. Reuse a
  size that a neighbouring component already uses. Do not invent a new one.
- No hex colour in a `className`. Six hex literals exist in `web/src`, in two files only:
  `components/family-tree/TreeCanvas.tsx` and `components/family-tree/SpouseEdge.tsx`. All six
  are props passed to `@xyflow/react`, not classes, for example `SpouseEdge.tsx:23`. Passing a
  colour to that library is the only accepted use.
- Keep the HTML semantic: `button` for an action, `a` for navigation, one `h1` per page,
  `ul` or `ol` for a list. A `div` with a click handler fails `T-07`.

## 10. Order of work for a new screen

1. Read the screen's entry in spec § 7. Most screens are already specified there.
2. Read spec § 5 and pick the requirements that apply.
3. Build the Server Component first. See `.claude/rules/nextjs.md` § 2.
4. Compose from `src/components/ui/` where a primitive exists, and add one where it does not.
5. Write the narrow layout, then add `md:` and `lg:`.
6. Add the loading, empty, and error states. `T-17` forbids a dead-end error state.
7. Check it at 200% text scale and in Vietnamese with full diacritics.
8. Write the tests.

## 11. Before you claim the work is done

The gate is the same one `web/CLAUDE.md` names. Styling changes do not get a lighter gate:

```bash
cd web && pnpm type-check && pnpm lint && pnpm depcruise \
  && pnpm test:unit && pnpm test:component && pnpm test:e2e && pnpm build
```

No command in that gate checks how anything looks. So for a visual change, also say plainly
what you did and did not verify in a browser. Do not report a colour or a layout as correct if
you only read the class name.
