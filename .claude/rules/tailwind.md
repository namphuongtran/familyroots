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

## 2. Most semantic colour tokens do nothing today

This is the most important thing on this page. Read it before you pick a colour class.

`globals.css` defines seventeen semantic colours in `@theme` as `hsl(var(--x))`, on lines 36 to
58: `accent`, `accent-foreground`, `background`, `border`, `card`, `card-foreground`,
`destructive`, `destructive-foreground`, `foreground`, `input`, `muted`, `muted-foreground`,
`popover`, `popover-foreground`, `ring`, `secondary`, and `secondary-foreground`. It then
defines those variables in `:root` as **hex strings**, on lines 124 to 147, for example
`--border: #e5e7eb`. `hsl()` takes hue, saturation, and lightness. So `hsl(#e5e7eb)` is not
valid CSS and the browser drops the declaration. `--secondary` is never defined at all.

The design spec § 2.8.1 measured this in a real browser on 2026-08-03. It probed thirteen of
the seventeen, and all thirteen resolved to the same inherited value. The shadcn convention
this was copied from stores bare channels, such as `45 33% 95%`, not hex.

**Dead. Do not use these classes:** `bg-background`, `text-foreground`, `border-border`,
`bg-card`, `bg-muted`, `text-muted-foreground`, `bg-popover`, `bg-accent`, `bg-secondary`,
`text-destructive`, `bg-destructive`, `ring-ring`, `border-input`. Every `*-foreground` variant
of those seventeen names is dead too, for example `text-card-foreground`.

**Working, because `@theme` holds a valid value and not an `hsl()` wrapper:** `bg-primary` and
the `primary-50` to `primary-900` ramp, `text-primary-foreground`, `bg-cream` and `cream-50` to
`cream-400`, `gold-100` to `gold-900`, `font-serif`, `font-sans`, `font-mono`, `rounded-sm`,
`rounded-md`, `rounded-lg`, and the three `animate-*` values. Note that § 5 forbids
`rounded-sm` on design grounds even though it resolves.

Rules that follow from this:

- Style with the working tokens plus Tailwind's own palette, for example `text-gray-900`.
- Do not add a new token in the `hsl(var(--x))` form. Put the value straight in `@theme`.
- Do not "fix" one dead token on its own. The two blocks disagree in a systematic way, and the
  disagreement with the spec is larger than a naming mismatch. `globals.css` makes primary the
  red `#c41e3a`. Spec § 2.1 makes primary the green `#3E5C38`, and puts red in a separate
  reserved family, `heritage: #A3182F`, for the thủy tổ marker and giỗ. Reconciling the two is a
  design-system change. Write an ADR under `docs/decisions/` first.
- If a screen looks right today while using a dead class, it looks right by inheritance.
  Do not read that as proof the class works.

## 3. Dark mode is declared but not built

- Line 3 of `globals.css` declares `@custom-variant dark (&:is(.dark *))`. That is the
  class-based form.
- No `.dark` selector exists anywhere in the stylesheet. Nothing in `web/src` sets a `dark`
  class.
- There are **zero** `dark:` utilities in `web/src` today. Measured 2026-08-13 across `.ts`,
  `.tsx`, and `.css`.

So:

- Do not write `dark:` classes. They cannot work, and § 2 means there is no working light
  palette to invert either.
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

**Fonts.** The font setup is broken. Do not copy it.

- `web/src/app/[locale]/layout.tsx:10` loads `Inter` through `next/font/google` with the
  Vietnamese subset and exposes `--font-inter`. Nothing reads `--font-inter`.
- `globals.css` instead hardcodes `font-family: 'Inter', 'Noto Sans', sans-serif` on `body`.
  A literal family name does not match the obfuscated name `next/font` generates. So the
  subsetted font is downloaded and then discarded.
- `Playfair Display` is named for headings in `globals.css` and is never loaded at all.
- `web/src/app/fonts/` holds `GeistVF.woff` and `GeistMonoVF.woff`. No file references them.
  They are leftovers from the project template. Do not wire them up.
- The mandate is **Plus Jakarta Sans** for headings and **Manrope** for body. Neither is used
  in `web/`. The mobile app does use them, and the files are already in the repository at
  `mobile/assets/fonts/PlusJakartaSans.ttf` and `mobile/assets/fonts/Manrope.ttf`, declared in
  `mobile/pubspec.yaml`. Design spec § 2.8.1 says these strings appear nowhere in the
  repository. That was true on 2026-08-03 and is no longer true.
- Do not add another `next/font` call as a drive-by fix. Fixing fonts means the mandated
  families, loaded through `next/font/local`, referenced through the CSS variable, applied on
  the document element. Check Vietnamese diacritic coverage in whichever files you ship. That
  is its own task.

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
