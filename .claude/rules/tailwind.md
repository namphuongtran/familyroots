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

## 2. The semantic colour tokens resolve, and the values are still the wrong values

Read this before you pick a colour class. Two different things were wrong here. One is fixed
and one is not, and mixing them up costs a rebuild.

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

Two rules follow, and the second one is the one that costs time:

- **Check a token by reading `globals.css`, not by reading a computed style.** The stylesheet holds
  the value unconditionally. `web/src/app/contrast.test.ts` does this, in the unit gate.
- **To see a token in a browser at all, a source file must use its class first.** Verified
  2026-08-13: with a throwaway file carrying `text-muted-foreground bg-destructive border-input`,
  the production build emitted `--color-muted-foreground:#6e6653`, `--color-destructive:#a32218`,
  and `--color-input:#8a8072`, each with the matching `.class{…var(--color-x)}` rule. So the values
  are correct and on demand, not dead. **S-007 is the seed for gating this**, and it must not be
  built on a runtime probe for the reason above.

**These classes work now:** `bg-background`, `text-foreground`, `border-border`, `bg-card`,
`bg-muted`, `text-muted-foreground`, `bg-popover`, `bg-accent`, `bg-secondary`,
`text-destructive`, `bg-destructive`, `ring-ring`, `border-input`, and every `*-foreground`
variant of the seventeen names. So do `bg-primary` and the `primary-50` to `primary-900` ramp,
`text-primary-foreground`, `bg-cream` and `cream-50` to `cream-400`, `gold-100` to `gold-900`,
`font-serif`, `font-sans`, `font-mono`, `rounded-sm`, `rounded-md`, `rounded-lg`, and the three
`animate-*` values. Note that § 5 forbids `rounded-sm` on design grounds even though it resolves.

**Contrast was fixed on 2026-08-13 by seed S-003, and it is now gated.** Three token values moved,
each to the value spec § 2.1 already names for that role:

| Token | Was | Is | Worst ratio, over the four grounds | Spec role |
|---|---|---|---|---|
| `muted-foreground` | `#6b7280` | `#6e6653` | 5.17 | `on-surface-muted` |
| `destructive` | `#ef4444` | `#a32218` | 7.50, both directions | `danger` |
| `input` | `#e5e7eb` | `#8a8072` | 3.53 | none: derived, see below |

The four grounds are `card` `#ffffff`, `cream` `#fdfbf7`, `background` `#f8f4ec`, and `muted`
`#f3f4f6`. A foreground has to clear all four, because `body` paints `cream` while the semantic
token calls the page `background`, and that disagreement is still open as part of S-004's renaming.

Four things to know before you touch these:

- **`destructive` is one digit from `heritage` `#a3182f`.** They are different families on purpose:
  `heritage` is ceremonial, for the thủy tổ marker and giỗ. Do not swap one for the other.
- **`border` stays light at `#e5e7eb`, and that is not an oversight.** The `*` rule in `globals.css`
  applies `border-border` to every element, so darkening it draws a line around everything and
  breaks the no-line rule in § 5. `input` is the token that carries a control's boundary, so `input`
  is the one held to 3:1. Spec § 2.8.1 F reasons the same way. Do not collapse the two values.
- **`input` `#8a8072` is derived, not quoted.** Spec § 2.1 offers no bordered-input value because it
  specifies a filled field instead, `surface-container-low` `#F4EFE4`. Spec § 2.8.1 F allows either
  branch, and S-003 took the darker-border branch as the smaller change. If S-005 adopts the fill,
  this token goes away.
- **`text-gold-*` is a lint error.** Gold is ornament: `gold-500` measures 2.10:1 on a white card,
  and the ramp does not clear 4.5 for text until `gold-800`. Tailwind v4 generates the text, fill,
  and border utilities from one variable, so the text scale cannot be trimmed on its own. The ban
  lives in `web/eslint.config.mjs` as `no-restricted-syntax`, matching any string literal, so
  `cn('text-gold-500')` is caught too. `bg-gold-*` and `border-gold-*` stay legal. For genuine gold
  text, spec § 2.1 names `gilt` `#8a6a16`, and it arrives with the S-005 rename.

**`web/src/app/contrast.test.ts` holds all of it in the unit gate.** It parses the hex values out of
`globals.css` and computes 30 pairs, so a value that drops below AA fails `pnpm test:unit`. Move the
token, never the threshold. It throws rather than skipping when a token is renamed, because a pair
table that silently resolves to nothing passes every assertion.

**Not fixed, and larger than the above.** The values still disagree with the design spec on the
biggest one, and S-001 deliberately did not repaint anything:

- `globals.css` makes primary the red `#c41e3a`. Spec § 2.1 makes primary the green `#3E5C38`,
  and puts red in a separate reserved family, `heritage: #A3182F`, for the thủy tổ marker and
  giỗ. Reconciling the two is a design-system change. Write an ADR under `docs/decisions/`
  first. That is seed S-004.
- `--secondary` and `--secondary-foreground` had no value at all, so S-001 gave them
  `#7a6248` and `#ffffff` from spec § 2.1's `secondary` row.
- **No screen uses the three tokens S-003 moved.** Counted 2026-08-13 across `web/src`, excluding
  `globals.css`: zero files reference `muted-foreground`, `bg-muted`, `bg-background`,
  `border-input`, `ring-ring`, or any `*-destructive` class. Forms draw their own boundary with
  `border-gray-300`, which measures 1.47:1 on white and fails WCAG 1.4.11. So S-003 changed no
  pixel, and the screens still have to be moved onto the tokens. That is seed S-035.

Rules that follow from this:

- **Do not add a new token in the `hsl(var(--x))` form. Put the value straight in `@theme`.**
  This is the defect that cost seventeen tokens, and nothing in the build catches it yet.
- Prefer the semantic token over Tailwind's own palette for new work, for example
  `text-muted-foreground` rather than `text-gray-500`. On a form boundary use `border-input`; it is
  the only value in the file that clears 3:1.
- A resolving token is not an approved colour. Check the value against spec § 2.1 before you
  build a screen on it, and expect S-004 to move `primary`.

## 3. Dark mode is declared but not built

- Line 3 of `globals.css` declares `@custom-variant dark (&:is(.dark *))`. That is the
  class-based form.
- No `.dark` selector exists anywhere in the stylesheet. Nothing in `web/src` sets a `dark`
  class.
- There are **zero** `dark:` utilities in `web/src` today. Measured 2026-08-13 across `.ts`,
  `.tsx`, and `.css`.

So:

- Do not write `dark:` classes. No `.dark` class is ever set, so they cannot work. The light
  palette does resolve since S-001, but § 2 says its values are still the wrong values, so
  there is nothing settled to invert yet either.
- Building dark mode is a deliberate task, not a side effect of a feature. Spec § 2.2 holds
  the dark palette. Spec § 2.8 asks for `@media (prefers-color-scheme: dark)` **and**
  `:root[data-theme="dark"]`, which contradicts the class-based variant on line 3. Settle
  that contradiction in the ADR, not in a component.
- Components must never branch on the theme in TypeScript. The theme is a CSS concern.

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

**One on-screen wordmark is still one unbreakable word**, at
`components/backoffice/BackofficeSidebar.tsx:35`. It sits behind a Supabase session, so nobody has
measured it at 320 px and 200% scale. It carries `text-xs`, so it is far less likely to overflow than
the `text-3xl` mark was, but "less likely" is not a measurement. Treat it as unverified, not as fixed.

**S-034 named a third wordmark that does not exist, and its line number for the second one was one
place off.** The seed's `Out of scope` line cites `components/layout/Sidebar.tsx:65` as a
`FamilyRoots` wordmark and `BackofficeSidebar.tsx:33` as the other. Read on 2026-08-13:
`Sidebar.tsx:65` holds `Gia Phả`, not `FamilyRoots`, and `grep -rn FamilyRoots src/` finds no match
in that file at all; the backoffice mark is on line 35. Nothing in the fix rested on either number,
which is precisely why nobody would have caught them. Grep for the string before you trust a cited
line here.

Known defect, so do not be surprised by it: `web/src/app/layout.tsx` hardcodes
`<html lang="en">`, and `web/src/app/[locale]/layout.tsx` renders a `<div>` instead of the
document element. That breaks `T-12`. `web/e2e/smoke.spec.ts:44` pins the current broken state
with `test.fail()`, so fixing `lang` turns that test red on purpose. Update the test in the
same pull request.

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
