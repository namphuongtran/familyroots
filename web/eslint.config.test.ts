import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { ESLint, type Linter } from 'eslint'
import { beforeAll, describe, expect, it } from 'vitest'
import { GOLD_IS_NEVER_TEXT, PALETTE_HAS_NO_DARK_VALUE } from './eslint.config.mjs'

/**
 * Whether `pnpm lint` refuses a Tailwind default-palette class, read on its outcome: issue #199.
 *
 * Each case lints a planted component through the real `eslint.config.mjs`, at a path under
 * `src/components/`, and reads which messages come back and on which line. Nothing here reads the
 * rule's selector or its family list back from the config. Those are settings, and
 * `.claude/rules/testing.md` is why this file exists instead.
 *
 * **The family list in this file is read independently.** The config takes the families from the
 * installed `tailwindcss/theme.css` on the `-50` step. The last case of the first block takes them
 * from every step, so a config that read a shorter list, or typed one from memory, leaves a family uncaught
 * and the case names it.
 *
 * **Naming.** `eslint.config.test.ts` runs under `vitest --project unit` (its include glob in
 * `vitest.config.mts` names it), beside the config it reads, as `playwright.config.test.ts` does.
 */

const WEB_ROOT = import.meta.dirname
const PLANT = 'src/components/__palette_plant__.tsx'

let eslint: ESLint

beforeAll(() => {
  eslint = new ESLint({ cwd: WEB_ROOT })
})

type Restricted = { line: number; message: string }

/** The `no-restricted-syntax` messages a planted file draws, each with its line. */
async function restrictedMessages(source: string): Promise<Restricted[]> {
  const [result] = await eslint.lintText(source, { filePath: PLANT })
  return result.messages
    .filter((m: Linter.LintMessage) => m.ruleId === 'no-restricted-syntax')
    .map((m: Linter.LintMessage) => ({ line: m.line, message: m.message }))
}

/** What a planted class on line 4 draws when the palette rule catches it. */
const CAUGHT_ON_LINE_4: Restricted[] = [{ line: 4, message: PALETTE_HAS_NO_DARK_VALUE }]

/** A component whose line 4 carries `expression`, the rest of it inert. */
function plant(expression: string): string {
  return [
    "const cn = (...parts: string[]) => parts.join(' ')",
    'export function Plant({ x }: { x: string }) {',
    '  return (',
    `    ${expression}`,
    '  )',
    '}',
    '',
  ].join('\n')
}

describe('a Tailwind default-palette class fails lint', () => {
  it.each([
    ['a className attribute', '<div className="text-gray-500" />'],
    ['a cn() argument', "<div className={cn('bg-blue-50', x)} />"],
    ['a template-literal segment', '<div className={`border-rose-200 ${x}`} />'],
  ])('in %s, naming the line', async (_shape, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual(CAUGHT_ON_LINE_4)
  })

  it.each([
    ['taupe', '<div className="text-taupe-500" />'],
    ['mist', '<div className="bg-mist-100" />'],
  ])('in %s, a family Tailwind added most recently', async (_family, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual(CAUGHT_ON_LINE_4)
  })

  it.each([
    ['a variant', 'hover:text-gray-500'],
    ['a dark: variant', 'dark:bg-zinc-900'],
    ['an opacity modifier', 'bg-red-500/50'],
    ['a one-side border', 'border-t-slate-200'],
    ['a ring offset', 'ring-offset-sky-300'],
    ['an inset shadow', 'inset-shadow-indigo-950'],
    ['the important suffix', 'text-amber-700!'],
  ])('behind %s', async (_shape, className) => {
    expect(await restrictedMessages(plant(`<div className="p-2 ${className}" />`))).toEqual(
      CAUGHT_ON_LINE_4,
    )
  })

  it('named as a variable in a style, the same colour by another name', async () => {
    const expression = "<div style={{ color: 'var(--color-gray-500)' }} />"
    expect(await restrictedMessages(plant(expression))).toEqual(CAUGHT_ON_LINE_4)
  })

  it('in every family the installed Tailwind declares, on every step', async () => {
    const require = createRequire(import.meta.url)
    const theme = readFileSync(require.resolve('tailwindcss/theme.css'), 'utf8')
    const classes = [...theme.matchAll(/--color-([a-z]+)-(\d+):/g)].map(
      ([, family, step]) => `bg-${family}-${step}`,
    )
    expect(classes.length).toBeGreaterThan(0)

    const source = classes.map((c, i) => `export const c${i} = '${c}'`).join('\n')
    const caught = new Set(
      (await restrictedMessages(source))
        .filter((m) => m.message === PALETTE_HAS_NO_DARK_VALUE)
        .map((m) => m.line),
    )
    const missed = classes.filter((_c, i) => !caught.has(i + 1))
    expect(missed).toEqual([])
  })
})

describe('what the palette rule leaves alone', () => {
  it('a comment that records a removed class', async () => {
    const source = [
      '// ADR-055: `editor` used to be `bg-blue-50 text-blue-700 border-blue-300`',
      '/* was `text-gray-500`, no dark value */',
      "export const role = 'editor'",
      '',
    ].join('\n')
    expect(await restrictedMessages(source)).toEqual([])
  })

  it.each([
    ['the project cream family', '<div className="bg-cream-100" />'],
    ['a gold stroke', '<div className="border-gold-300" />'],
    ['a semantic token', '<div className="bg-muted text-muted-foreground border-border" />'],
    ['a status token', '<div className="bg-success/10 text-destructive" />'],
  ])('%s', async (_subject, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual([])
  })

  it('gold text, which draws the gold rule and not this one', async () => {
    expect(await restrictedMessages(plant('<div className="text-gold-500" />'))).toEqual([
      { line: 4, message: GOLD_IS_NEVER_TEXT },
    ])
  })
})
