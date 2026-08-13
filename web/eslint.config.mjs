import nextConfig from 'eslint-config-next'

/*
 * Seed S-003. Gold is ornament, and the palette cannot express that on its own:
 * Tailwind v4 generates `text-gold-500`, `bg-gold-500`, and `border-gold-500`
 * from the single `--color-gold-500` variable, so the text scale cannot be
 * trimmed without losing the fills the design does want. Measured 2026-08-13,
 * gold-500 gives 2.10:1 on a white card, which fails at every size. Spec § 2.1
 * splits the role in two, `gilt-decor` #d4af37 for ornament and `gilt` #8a6a16
 * for gold text, and that split arrives with the S-005 rename. Until it does,
 * there is no legal gold text and this rule is what says so.
 *
 * It matches any string literal, so `cn('text-gold-500')` is caught as well as
 * a `className` attribute. It cannot see a class name assembled at runtime.
 */
const GOLD_IS_NEVER_TEXT =
  'Gold is ornament, never text: gold-500 measures 2.10:1 on white. ' +
  'Use bg-gold-* or border-gold-* for a fill or a stroke. For gold text, wait for ' +
  'spec § 2.1 `gilt` #8a6a16 to land with S-005. See .claude/rules/tailwind.md § 2.'

const config = [
  ...nextConfig,
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: 'Literal[value=/text-gold-/]', message: GOLD_IS_NEVER_TEXT },
        { selector: 'TemplateElement[value.raw=/text-gold-/]', message: GOLD_IS_NEVER_TEXT },
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

export default config
