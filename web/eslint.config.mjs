import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import nextConfig from 'eslint-config-next'

/*
 * Gold is ornament, and the palette cannot express that on its own:
 * Tailwind v4 generates `text-gold-500`, `bg-gold-500`, and `border-gold-500`
 * from the single `--color-gold-500` variable, so the text scale cannot be
 * trimmed without losing the fills the design does want. Measured 2026-08-13,
 * gold-500 gives 2.10:1 on a white card, which fails at every size. Spec § 2.1
 * splits the role in two, `gilt-decor` #d4af37 for ornament and `gilt` #8a6a16
 * for gold text, and that split arrives with the leaf-green rename. Until it does,
 * there is no legal gold text and this rule is what says so.
 *
 * It matches any string literal, so `cn('text-gold-500')` is caught as well as
 * a `className` attribute. It cannot see a class name assembled at runtime.
 */
const GOLD_IS_NEVER_TEXT =
  'Gold is ornament, never text: gold-500 measures 2.10:1 on white. ' +
  'Use bg-gold-* or border-gold-* for a fill or a stroke. For gold text, wait for ' +
  'spec § 2.1 `gilt` #8a6a16 to land with the rename. See .claude/rules/tailwind.md § 2.'

/*
 * A Tailwind default-palette colour has no dark value. ADR-045 switches the theme by overriding
 * tokens under `prefers-color-scheme`, and `text-gray-500` names no token, so it stays light in a
 * dark screen while every gate is green. S-038 (`586fff0`) and ADR-055 moved 393 such classes onto
 * semantic tokens, and re-counted 2026-10-07 none is left outside a comment. This rule keeps it
 * that way (#199).
 *
 * The families are read from the installed Tailwind, not typed here: every `--color-<family>-50`
 * that `tailwindcss/theme.css` declares, read each time lint loads. At tailwindcss 4.3.3, which
 * `pnpm-lock.yaml` resolves for `package.json`'s `^4.3.3`, it read 26 families on 2026-10-07, `red` to `stone` plus `mauve`, `olive`, `mist` and `taupe`, the four a list
 * typed from memory misses. The project's `gold` and `cream` are declared in `globals.css`, not
 * there, so they stay legal, and GOLD_IS_NEVER_TEXT keeps covering gold text. A theme file that
 * yields no family throws here, because a rule over an empty list bans nothing and lints green.
 *
 * It matches `<utility>-<family>-<step>` behind any utility prefix, so `border-t-gray-200`,
 * `ring-offset-sky-300` and `hover:text-gray-500` are caught with the plain forms, and so is a
 * `var(--color-gray-500)`, the same colour by another name. Like GOLD_IS_NEVER_TEXT it matches any
 * string literal or template segment, so a `className`, a `cn()` argument and a template literal are
 * all caught, and a comment, which is not a literal, is not. It cannot see a class name assembled at
 * runtime, such as `bg-${tone}-50`. None existed on 2026-10-07.
 */
const TAILWIND_THEME = readFileSync(
  createRequire(import.meta.url).resolve('tailwindcss/theme.css'),
  'utf8',
)
const PALETTE_FAMILIES = [...TAILWIND_THEME.matchAll(/--color-([a-z]+)-50:/g)].map(([, f]) => f)
if (PALETTE_FAMILIES.length === 0) {
  throw new Error('eslint.config.mjs: tailwindcss/theme.css declared no --color-<family>-50.')
}
const PALETTE_CLASS_PATTERN = `\\b(?:[a-z]+-)+(?:${PALETTE_FAMILIES.join('|')})-\\d{2,3}\\b`
const PALETTE_HAS_NO_DARK_VALUE =
  'A Tailwind palette colour has no dark value, so it stays light in dark mode. ' +
  'Use a semantic token: text-muted-foreground, not text-gray-500. For a hue with no token, ' +
  'see ADR-055. See .claude/rules/tailwind.md § 2 and § 3.'

const config = [
  /*
   * Playwright was given a second Next.js dist dir so the banner spec can
   * run a dev server with the Supabase vars forced empty. `eslint-config-next`
   * ignores `.next/`, but it cannot know about a second one, so `eslint .` swept
   * the generated bundles and reported 49 errors from code nobody wrote. That
   * made the lint gate depend on whether `test:e2e` had run first: green on a
   * clean checkout, red on a developer's machine. A gate whose answer depends on
   * execution order is not a gate. Found and fixed here, 2026-08-22.
   * The directory name is the same literal as `PLAYWRIGHT_SECOND_DIST_DIR` in
   * `playwright.config.ts:51` and `/.next-banner-e2e/` in `.gitignore:17`.
   */
  /*
   * A later change hit the identical problem with a *third* dist dir and the comment above
   * predicted it: `.next-auth-e2e/` is the authenticated e2e server's build directory
   * (`playwright.config.ts`, `authStackEnv()`), and `pnpm lint` swept it for **78 errors**
   * from generated bundles on 2026-08-26, after one `pnpm test:e2e:auth` run. Same defect,
   * same shape: the lint result depended on whether the e2e suite had run first. Every extra
   * `PLAYWRIGHT_SECOND_DIST_DIR` value needs a line here, in `.gitignore`, and in
   * `tsconfig.json`'s `include`.
   */
  { ignores: ['.next-banner-e2e/**', '.next-auth-e2e/**'] },
  ...nextConfig,
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: 'Literal[value=/text-gold-/]', message: GOLD_IS_NEVER_TEXT },
        { selector: 'TemplateElement[value.raw=/text-gold-/]', message: GOLD_IS_NEVER_TEXT },
        {
          selector: `Literal[value=/${PALETTE_CLASS_PATTERN}/]`,
          message: PALETTE_HAS_NO_DARK_VALUE,
        },
        {
          selector: `TemplateElement[value.raw=/${PALETTE_CLASS_PATTERN}/]`,
          message: PALETTE_HAS_NO_DARK_VALUE,
        },
      ],
    },
  },
  {
    files: ['src/domain/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            '@/app/*',
            '@/components/*',
            '@/lib/api/*',
            '@/lib/hooks/*',
            '@/store/*',
            '@/infrastructure/*',
            '@tanstack/*',
            'next/*',
            'react*',
            'axios',
            '@supabase/*',
          ],
        },
      ],
    },
  },
  {
    files: ['src/application/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            '@/app/*',
            '@/components/*',
            '@/lib/api/*',
            '@/lib/hooks/*',
            '@/store/*',
            '@/infrastructure/*',
            'next/*',
            'react*',
            'axios',
            '@supabase/*',
          ],
        },
      ],
    },
  },
]

export { GOLD_IS_NEVER_TEXT, PALETTE_HAS_NO_DARK_VALUE }
export default config
