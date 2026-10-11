import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { ESLint, type Linter } from 'eslint'
import { beforeAll, describe, expect, it } from 'vitest'
import {
  GOLD_IS_NEVER_TEXT,
  PALETTE_HAS_NO_DARK_VALUE,
  SINGLE_VALUE_HAS_NO_DARK_VALUE,
} from './eslint.config.mjs'

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
 * **#238 added `white` and `black`**, which have no step for the `-50` read to find. The block
 * for them reads them independently too: every `--color-<name>` in the theme with no step. The
 * block after it holds the `whitespace-*` utilities, which share the letters and are no colour.
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
const PALETTE_CAUGHT_ON_LINE_4: Restricted[] = [{ line: 4, message: PALETTE_HAS_NO_DARK_VALUE }]

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

/** The classes, planted one to a line, for which lint draws no `message`. */
async function uncaught(classes: string[], message: string): Promise<string[]> {
  const source = classes.map((c, i) => `export const c${i} = '${c}'`).join('\n')
  const caught = new Set(
    (await restrictedMessages(source)).filter((m) => m.message === message).map((m) => m.line),
  )
  return classes.filter((_c, i) => !caught.has(i + 1))
}

describe('a Tailwind default-palette class fails lint', () => {
  it.each([
    ['a className attribute', '<div className="text-gray-500" />'],
    ['a cn() argument', "<div className={cn('bg-blue-50', x)} />"],
    ['a template-literal segment', '<div className={`border-rose-200 ${x}`} />'],
  ])('in %s, naming the line', async (_shape, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual(PALETTE_CAUGHT_ON_LINE_4)
  })

  it.each([
    ['taupe', '<div className="text-taupe-500" />'],
    ['mist', '<div className="bg-mist-100" />'],
  ])('in %s, a family Tailwind added most recently', async (_family, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual(PALETTE_CAUGHT_ON_LINE_4)
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
      PALETTE_CAUGHT_ON_LINE_4,
    )
  })

  it('named as a variable in a style, the same colour by another name', async () => {
    const expression = "<div style={{ color: 'var(--color-gray-500)' }} />"
    expect(await restrictedMessages(plant(expression))).toEqual(PALETTE_CAUGHT_ON_LINE_4)
  })

  it('in every family the installed Tailwind declares, on every step', async () => {
    const require = createRequire(import.meta.url)
    const theme = readFileSync(require.resolve('tailwindcss/theme.css'), 'utf8')
    const classes = [...theme.matchAll(/--color-([a-z]+)-(\d+):/g)].map(
      ([, family, step]) => `bg-${family}-${step}`,
    )
    expect(classes.length).toBeGreaterThan(0)
    expect(await uncaught(classes, PALETTE_HAS_NO_DARK_VALUE)).toEqual([])
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

/**
 * #238. `white` and `black` are one value each, with no `-50` step, so the palette rule above
 * never saw them, and neither has a dark value: a `bg-white` header stays white on a dark screen.
 */
const SINGLE_VALUE_CAUGHT_ON_LINE_4: Restricted[] = [
  { line: 4, message: SINGLE_VALUE_HAS_NO_DARK_VALUE },
]

describe('a white or black colour class fails lint', () => {
  it.each([
    ['bg-white', '<header className="border-b bg-white px-6" />'],
    ['text-white', "<button className={cn('bg-destructive text-white', x)} />"],
    ['bg-black/40', '<div className={`fixed inset-0 bg-black/40 ${x}`} />'],
  ])('%s, naming the line', async (_class, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual(SINGLE_VALUE_CAUGHT_ON_LINE_4)
  })

  it.each([
    ['a variant', 'hover:bg-white'],
    ['a gradient stop', 'from-black/40'],
    ['an opacity modifier', 'bg-white/80'],
    ['a ring offset', 'ring-offset-white'],
    ['a one-side border', 'border-t-black'],
    ['the important suffix', 'text-white!'],
  ])('behind %s', async (_shape, className) => {
    expect(await restrictedMessages(plant(`<div className="p-2 ${className}" />`))).toEqual(
      SINGLE_VALUE_CAUGHT_ON_LINE_4,
    )
  })

  it('named as a variable in a style, the same colour by another name', async () => {
    const expression = "<div style={{ background: 'var(--color-black)' }} />"
    expect(await restrictedMessages(plant(expression))).toEqual(SINGLE_VALUE_CAUGHT_ON_LINE_4)
  })

  /**
   * Read independently of the config: every `--color-<name>` the installed theme declares that
   * ends in no step. At tailwindcss 4.3.3 that is `black` and `white`, and a colour a later
   * Tailwind adds the same way is named here if the config does not read it.
   */
  it('for every single-value colour the installed Tailwind declares', async () => {
    const require = createRequire(import.meta.url)
    const theme = readFileSync(require.resolve('tailwindcss/theme.css'), 'utf8')
    const classes = [...theme.matchAll(/--color-([a-z-]+):/g)]
      .map(([, name]) => name)
      .filter((name) => !/-\d+$/.test(name))
      .map((name) => `bg-${name}`)
    expect(classes).toEqual(expect.arrayContaining(['bg-black', 'bg-white']))
    expect(await uncaught(classes, SINGLE_VALUE_HAS_NO_DARK_VALUE)).toEqual([])
  })

  it('beside a palette class, each rule naming its own', async () => {
    const expression = '<div className="bg-gray-500 bg-white" />'
    const messages = await restrictedMessages(plant(expression))
    expect(messages).toHaveLength(2)
    expect(messages).toEqual(
      expect.arrayContaining([
        { line: 4, message: PALETTE_HAS_NO_DARK_VALUE },
        { line: 4, message: SINGLE_VALUE_HAS_NO_DARK_VALUE },
      ]),
    )
  })
})

describe('what the white and black rule leaves alone', () => {
  it.each([
    'whitespace-nowrap',
    'whitespace-pre-line',
    'whitespace-pre-wrap',
    'whitespace-normal',
    'whitespace-pre',
    'whitespace-break-spaces',
  ])('%s, which is no colour', async (className) => {
    expect(await restrictedMessages(plant(`<p className="${className}" />`))).toEqual([])
  })

  it.each([
    ['the scrim token', '<div className="fixed inset-0 bg-scrim" />'],
    [
      'the scrim as a gradient stop',
      '<div className="bg-linear-to-t from-scrim to-transparent" />',
    ],
    ['a card at an alpha', '<span className="bg-card/80 hover:bg-card" />'],
    [
      'the ink on a destructive fill',
      '<span className="bg-destructive text-destructive-foreground" />',
    ],
    ['a colour that follows its context', '<span className="border-current to-transparent" />'],
  ])('%s', async (_subject, expression) => {
    expect(await restrictedMessages(plant(expression))).toEqual([])
  })

  it('a comment that records a removed class', async () => {
    const source = [
      '// #238: the header was `bg-white`, and the scrims `bg-black/40`',
      "export const surface = 'card'",
      '',
    ].join('\n')
    expect(await restrictedMessages(source)).toEqual([])
  })
})
