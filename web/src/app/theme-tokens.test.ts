import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/postcss'
import postcss from 'postcss'
import { describe, expect, it } from 'vitest'

/**
 * the token gate. **Seventeen dead colour tokens survived every gate this repository
 * runs.** On 2026-08-13 `pnpm type-check`, `pnpm lint`, `pnpm depcruise`, and
 * `pnpm build` all passed over a `globals.css` in which those seventeen were
 * declared as `hsl(var(--x))` over values that were hex strings. `hsl(#e5e7eb)`
 * is not valid CSS, so the browser dropped the whole declaration and every one
 * of the seventeen painted the inherited body colour instead. The token fix fixed
 * the instance. This file closes the class: CSS that a browser drops is not a
 * build error, so nothing but a check written for it will ever see it.
 *
 * ## Why this compiles the stylesheet instead of reading it
 *
 * The seed offered two mechanisms and called this one closer to what it asks
 * for. Reading the source can only judge the text an author typed. Compiling
 * judges what the browser is actually handed, which is a different thing in
 * three ways that have all bitten this repository:
 *
 * 1. A token can be declared and still never reach the build. Tailwind v4 emits
 *    an `@theme` variable only when a generated rule references it, and it drops
 *    a namespace it does not understand without a word. Reading `@theme` cannot
 *    tell you that.
 * 2. Lightning CSS rewrites values on the way out. It resolves a `var()` inside
 *    a `color-mix()` when it emits the pre-`color-mix()` sRGB fallback, and seed
 *    the dark-palette change measured it resolving one against the wrong scope. The emitted text
 *    is the only place that is visible.
 * 3. A value can be a literal and still be nonsense. `#ff` and `hsl(#8a8072)`
 *    are both literals.
 *
 * ## Why this is not a browser probe, which is the trap
 *
 * The seed's own `Sources` line recommends a Playwright probe and then withdraws
 * it, and the withdrawal is right. Tailwind emits an `@theme` variable only when
 * a generated rule references it, so a token that no class in `web/src` uses is
 * **absent** from the built CSS, and `color: var(--color-x)` in a page then
 * returns the inherited body colour. Measured 2026-08-13 on `/vi/login`, in
 * `next dev` and in a production build alike: fifteen of the seventeen returned
 * `lab(8.11897 0.811279 -12.254)`, and every one of the fifteen was healthy. So
 * a probe cannot tell "no class asks for it yet" apart from "the declaration was
 * dropped", and a gate built on one would report a defect on a healthy tree.
 *
 * This file removes that ambiguity at the root rather than working around it: it
 * **generates** the class set, one `bg-*`, `font-*`, `rounded-*`, or `animate-*`
 * candidate per declared token, and feeds it to Tailwind through
 * `@source inline(...)`. Every token is therefore referenced, so absence from
 * the emitted CSS means the build dropped it and nothing else.
 *
 * ## What it does not cover
 *
 * Whether a token is the *right* colour. `contrast.test.ts` measures the pairs
 * against WCAG AA, and ADR-041 decides the values. This file only asks whether a
 * name resolves to something a browser can paint.
 *
 * Whether the palette reaches a real screen. `e2e/dark-theme.spec.ts` and
 * `e2e/fonts.spec.ts` answer that, and only an engine can: a stylesheet holding
 * both palettes cannot tell you which one won the cascade.
 */

// `fileURLToPath`, not `.pathname`: this repository lives under a path with a
// space in it, and a URL keeps that percent-encoded.
const APP = fileURLToPath(new URL('.', import.meta.url))
const GLOBALS = `${APP}globals.css`

const SOURCE = readFileSync(GLOBALS, 'utf8')

/**
 * Comments are stripped before any name is read, for the same reason
 * `contrast.test.ts` strips them: `globals.css` quotes hex values and token
 * names in prose, at length and on purpose, so a parser that reads the comments
 * is one reworded sentence away from checking a token no rule declares.
 * Replaced with a newline rather than nothing, so a comment sitting between two
 * declarations cannot splice them together.
 */
const uncommented = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, '\n')

/**
 * Returns the body of the block that `opener` opens, found by counting braces.
 *
 * A brace walk rather than a lazy `{([^}]*)}` because `@theme` contains nested
 * `@keyframes` blocks. Scoped rather than file-wide because `globals.css` holds
 * two colour palettes since ADR-045, and a file-wide read of a two-palette file
 * silently measures whichever came last. The dark-palette change planted exactly that in
 * `contrast.test.ts` on 2026-08-21 and all 156 cases still passed.
 */
const blockBody = (source: string, opener: string, what: string): string => {
  const at = source.indexOf(opener)
  if (at === -1) {
    throw new Error(
      `${what} holds no \`${opener}\` block. This check cannot gate what it cannot read, ` +
        `so a missing scope is a failure rather than an empty pass.`,
    )
  }
  const brace = at + opener.length - 1
  let depth = 0
  for (let cursor = brace; cursor < source.length; cursor++) {
    if (source[cursor] === '{') depth++
    else if (source[cursor] === '}') {
      depth--
      if (depth === 0) return source.slice(brace + 1, cursor)
    }
  }
  throw new Error(`\`${opener}\` in ${what} is never closed.`)
}

const DARK_MEDIA = '@media (prefers-color-scheme: dark) {'

const THEME_SOURCE = blockBody(uncommented(SOURCE), '@theme {', 'globals.css')
const DARK_SOURCE = blockBody(uncommented(SOURCE), DARK_MEDIA, 'globals.css')

/** Every `--name: value;` in a block, in source order, duplicates kept. */
const declarations = (scope: string): [string, string][] =>
  [...scope.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()])

/** Last declaration wins, which is how the cascade reads a single scope. */
const asMap = (pairs: [string, string][]): Map<string, string> => new Map(pairs)

/**
 * The utility prefix each `@theme` namespace generates, which is how a token is
 * made to appear in the build at all.
 *
 * A namespace missing from this map throws rather than being skipped. That is
 * the difference between a gate and a gate that scanned nothing: the day someone
 * adds `--spacing-*` or `--text-*` to `@theme`, this check must stop and be
 * extended, not quietly cover four namespaces out of five.
 */
const UTILITY_PREFIX = new Map([
  // `bg-`, not `text-`: `bg-gold-*` is legal and `text-gold-*` is a lint error
  // (`web/eslint.config.mjs`). Either utility proves the same thing,
  // so this file uses the one the repository allows for every colour.
  ['color', 'bg-'],
  ['font', 'font-'],
  ['radius', 'rounded-'],
  ['animate', 'animate-'],
])

type Token = {
  readonly name: string
  readonly namespace: string
  readonly utility: string
  readonly value: string
}

const THEME_TOKENS: readonly Token[] = declarations(THEME_SOURCE).map(([name, value]) => {
  const namespace = name.slice(0, name.indexOf('-'))
  const prefix = UTILITY_PREFIX.get(namespace)
  if (prefix === undefined) {
    throw new Error(
      `\`@theme\` declares --${name}, whose \`${namespace}\` namespace this check does not know ` +
        `how to reference. Add it to UTILITY_PREFIX with the utility Tailwind generates for it. ` +
        `A namespace this file skips is a namespace nothing gates.`,
    )
  }
  return { name, namespace, utility: prefix + name.slice(namespace.length + 1), value }
})

const COLOUR_TOKENS = THEME_TOKENS.filter(({ namespace }) => namespace === 'color')

/**
 * Two variables `globals.css` reads that no stylesheet declares. `next/font`
 * generates the family name at build time and `layout.tsx` puts it on the
 * document element, so the value only exists at runtime. A case below asserts
 * that `layout.tsx` still declares both, because an allow-list nobody checks is
 * just a hole with a comment over it.
 */
const RUNTIME_INJECTED = ['--font-plus-jakarta-sans', '--font-manrope'] as const

/* ------------------------------------------------------------------------- *
 * The build
 * ------------------------------------------------------------------------- */

/**
 * `source(none)` turns off automatic content detection, and the generated
 * candidate list replaces it. Both halves are deliberate. Detection would make
 * what is emitted depend on which classes `web/src` happens to use today, which
 * is the very ambiguity that makes a runtime probe useless here, and it would
 * make a gate that reads one stylesheet walk the whole repository to do it.
 */
const patched = ((): string => {
  const withSourceNone = SOURCE.replace(
    "@import 'tailwindcss';",
    "@import 'tailwindcss' source(none);",
  )
  if (withSourceNone === SOURCE) {
    throw new Error(
      `globals.css no longer opens with \`@import 'tailwindcss';\`, so this check could not ` +
        `pin the content sources. Update the patch rather than letting the build scan the repo.`,
    )
  }
  const candidates = THEME_TOKENS.map(({ utility }) => utility).join(' ')
  return `@source inline("${candidates}");\n${withSourceNone}`
})()

const BUILT = uncommented((await postcss([tailwindcss()]).process(patched, { from: GLOBALS })).css)

const BUILT_DARK = blockBody(BUILT, DARK_MEDIA, 'the built stylesheet')
const BUILT_LIGHT = BUILT.replace(BUILT_DARK, '')

/**
 * Every occurrence, not a map, because Lightning CSS emits a declaration twice
 * when it writes an `@supports` fallback beside it, and a defect in the fallback
 * branch is a defect. Reaching the fallback branch is exactly what an older
 * browser does.
 */
const LIGHT_DECLARATIONS = declarations(BUILT_LIGHT)
const DARK_DECLARATIONS = declarations(BUILT_DARK)

const LIGHT_VARS = asMap(LIGHT_DECLARATIONS)
/** Dark overrides only the names it declares, so a dark screen resolves both. */
const DARK_VARS = asMap([...LIGHT_DECLARATIONS, ...DARK_DECLARATIONS])

/**
 * `emitted` is what that scope declares itself; `vars` is what it resolves
 * through, which for dark is light overlaid by the overrides, exactly as the
 * cascade reads it. A token dark does not override has no dark declaration to
 * judge, and the light case already judged the value it inherits.
 */
const SCOPES = [
  { scope: 'light', vars: LIGHT_VARS, emitted: LIGHT_DECLARATIONS },
  { scope: 'dark', vars: DARK_VARS, emitted: DARK_DECLARATIONS },
] as const

/* ------------------------------------------------------------------------- *
 * Resolution
 * ------------------------------------------------------------------------- */

const RUNTIME = 'RuntimeInjectedFamily'

/**
 * Substitutes every `var()` against the scope until none is left, and throws
 * naming the token and the variable it reached for when one is not declared.
 *
 * That throw is the token fix defect caught at its root: `--color-border` read
 * `hsl(var(--border))` while `--border` lived in a `:root` block that no longer
 * exists, so the value could never become a colour whatever `hsl()` did with it.
 */
const resolve = (token: string, value: string, vars: Map<string, string>): string => {
  let current = value
  for (let pass = 0; pass < 10; pass++) {
    if (!current.includes('var(')) return current
    current = current.replace(/var\((--[a-z0-9-]+)\)/g, (whole, name: string) => {
      if ((RUNTIME_INJECTED as readonly string[]).includes(name)) return RUNTIME
      const declared = vars.get(name.slice(2))
      if (declared === undefined) {
        throw new Error(
          `--${token} reads ${whole}, and no scope of the built stylesheet declares ${name}. ` +
            `The declaration cannot resolve, so the browser drops it and the token paints ` +
            `whatever it inherits. Put the value in \`@theme\` rather than behind an indirection.`,
        )
      }
      return declared
    })
  }
  throw new Error(`--${token} nests \`var()\` more than ten deep, or refers back to itself.`)
}

/* ------------------------------------------------------------------------- *
 * Is this a colour?
 * ------------------------------------------------------------------------- */

/**
 * Deliberately short. Every colour in `globals.css` is a hex literal or a
 * `color-mix()` of one, and the only bare words in the file are the `black` and
 * `white` the two hover mixes shift toward. Extending this list is cheap and a
 * failure here says so by name, which is the right trade against a 148-entry
 * table nobody reads.
 */
const KEYWORDS = new Set([
  'transparent',
  'currentcolor',
  'black',
  'white',
  'red',
  'green',
  'blue',
  'yellow',
  'gray',
  'grey',
  'silver',
  'maroon',
  'olive',
  'lime',
  'aqua',
  'teal',
  'navy',
  'fuchsia',
  'purple',
])

/** `<number>`, `<percentage>`, `<angle>`, or the `none` keyword. */
const NUMERIC = /^(none|[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?(%|deg|rad|grad|turn)?)$/i

/** Functions whose arguments are numbers, so a colour inside one is the defect. */
const NUMERIC_FUNCTIONS = new Set([
  'rgb',
  'rgba',
  'hsl',
  'hsla',
  'hwb',
  'lab',
  'lch',
  'oklab',
  'oklch',
])

/**
 * Splits on a separator that is not inside brackets, so a nested `color-mix()`
 * stays one piece. A plain `split` tears one apart at its own commas and spaces.
 */
const topLevel = (args: string, separator: RegExp): string[] => {
  const parts: string[] = []
  let depth = 0
  let start = 0
  for (let at = 0; at < args.length; at++) {
    if (args[at] === '(') depth++
    else if (args[at] === ')') depth--
    else if (depth === 0 && separator.test(args[at])) {
      parts.push(args.slice(start, at))
      start = at + 1
    }
  }
  parts.push(args.slice(start))
  return parts.map((part) => part.trim()).filter((part) => part.length > 0)
}

const CALL = /^([a-z-]+)\(([\s\S]*)\)$/i

/**
 * True when a browser can paint this value.
 *
 * The historical defect is what this is shaped around: `hsl(#e5e7eb)` is a
 * literal, it is well formed as text, and it is not a colour, because `hsl()`
 * takes three numbers. So a function's arguments are checked against what that
 * function accepts rather than merely counted.
 */
const isColour = (value: string): boolean => {
  const trimmed = value.trim()
  if (/^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(trimmed)) return true
  if (KEYWORDS.has(trimmed.toLowerCase())) return true

  const call = CALL.exec(trimmed)
  if (call === null) return false
  const [, fn, args] = call
  const name = fn.toLowerCase()

  if (name === 'color-mix') {
    const parts = topLevel(args, /,/)
    if (parts.length !== 3) return false
    const [space, ...colours] = parts
    if (!/^in [a-z-]+( (shorter|longer|increasing|decreasing) hue)?$/i.test(space)) return false
    return colours.every((part) => {
      // `<color> <percentage>?`, in either order per the spec; only the colour is
      // ours to judge.
      const words = topLevel(part, /\s/).filter((word) => !word.endsWith('%'))
      return words.length === 1 && isColour(words[0])
    })
  }

  if (NUMERIC_FUNCTIONS.has(name)) {
    const words = args
      .split(/[\s,/]+/)
      .map((word) => word.trim())
      .filter((word) => word.length > 0)
    return words.length > 0 && words.every((word) => NUMERIC.test(word))
  }

  if (name === 'color') {
    const words = args.split(/[\s,/]+/).filter((word) => word.length > 0)
    return words.length > 1 && words.slice(1).every((word) => NUMERIC.test(word))
  }

  return false
}

/* ------------------------------------------------------------------------- *
 * The cases
 * ------------------------------------------------------------------------- */

describe('the build was read at all', () => {
  /**
   * Guards every case below. A compile that emitted nothing, or a scope regex
   * that matched nothing, turns each `it.each` into an empty pass. There were 50
   * `@theme` tokens on 2026-08-22, 41 of them colours.
   */
  it('found the tokens, the utilities, and both scopes', () => {
    expect(THEME_TOKENS.length).toBeGreaterThanOrEqual(50)
    expect(COLOUR_TOKENS.length).toBeGreaterThanOrEqual(41)
    expect(LIGHT_DECLARATIONS.length).toBeGreaterThanOrEqual(50)
    expect(DARK_DECLARATIONS.length).toBeGreaterThanOrEqual(25)
  })
})

describe('every `@theme` token reaches the built stylesheet', () => {
  it.each(THEME_TOKENS)('--$name is emitted, and .$utility generates', ({ name, utility }) => {
    expect(
      BUILT.includes(`.${utility} {`),
      `Tailwind generated no .${utility} rule, so nothing in the app can reach --${name}. ` +
        `The token is declared and dead.`,
    ).toBe(true)

    expect(
      LIGHT_VARS.has(name),
      `.${utility} is generated and reads var(--${name}), but the build declares no --${name}. ` +
        `Every rule using it resolves to nothing.`,
    ).toBe(true)
  })
})

describe.each(SCOPES)(
  'every colour token resolves to a colour in $scope',
  ({ scope, vars, emitted }) => {
    it.each(COLOUR_TOKENS)('--$name', ({ name }) => {
      expect(vars.has(name), `nothing a ${scope} screen reads declares --${name}`).toBe(true)

      // Every occurrence, so an `@supports` fallback branch is judged too.
      const occurrences = emitted.filter(([declared]) => declared === name)

      for (const [, value] of occurrences) {
        const resolved = resolve(name, value, vars)
        expect(
          isColour(resolved),
          `${scope}: --${name} is \`${value}\`, which resolves to \`${resolved}\`. That is not a ` +
            `colour, so the browser drops the declaration and every element using it paints what ` +
            `it inherits. This is the defect that killed seventeen tokens; see ` +
            `.claude/rules/tailwind.md § 2.`,
        ).toBe(true)
      }
    })
  },
)

describe('the non-colour tokens point at something that exists', () => {
  it.each(THEME_TOKENS.filter(({ namespace }) => namespace !== 'color'))(
    '--$name resolves',
    ({ name }) => {
      const value = LIGHT_VARS.get(name)
      expect(value, `the build declares no --${name}`).toBeDefined()
      // Throws, naming the token and the missing variable, when it cannot.
      expect(() => resolve(name, value ?? '', LIGHT_VARS)).not.toThrow()
    },
  )

  /**
   * An `--animate-*` value names a `@keyframes` rule. A name with no rule behind
   * it is the same defect in a different namespace: the class exists, the
   * animation does nothing, and nothing in the build says so.
   */
  it.each(THEME_TOKENS.filter(({ namespace }) => namespace === 'animate'))(
    '--$name names a @keyframes block that exists',
    ({ name }) => {
      const keyframes = (LIGHT_VARS.get(name) ?? '').split(/\s+/)[0]
      expect(
        BUILT.includes(`@keyframes ${keyframes} {`),
        `--${name} runs \`${keyframes}\`, and the build holds no \`@keyframes ${keyframes}\`.`,
      ).toBe(true)
    },
  )

  /**
   * The two families are read through variables `next/font` generates at build
   * time, so no stylesheet can declare them and `resolve` allow-lists them. This
   * is the case that keeps the allow-list honest.
   */
  it.each(RUNTIME_INJECTED)('%s is still set by layout.tsx', (variable) => {
    expect(readFileSync(`${APP}layout.tsx`, 'utf8')).toContain(`variable: '${variable}'`)
  })
})

/**
 * A dark override of a name `@theme` does not declare generates no utility, so
 * it is dead in exactly the way this seed is about. `contrast.test.ts` cannot
 * see it: its `DARK` map inherits from `LIGHT`, so an extra dark name reads as a
 * token that simply has no light value.
 */
describe('the dark scope overrides tokens that exist', () => {
  const THEME_NAMES = new Set(THEME_TOKENS.map(({ name }) => name))

  it('declares no colour `@theme` never declared', () => {
    const orphans = declarations(DARK_SOURCE)
      .map(([name]) => name)
      .filter((name) => !THEME_NAMES.has(name))

    expect(
      orphans,
      `the dark scope declares these, and \`@theme\` does not, so Tailwind generates no ` +
        `utility for them and nothing can paint them: ${orphans.join(', ')}`,
    ).toEqual([])
  })
})

/**
 * The validator's own negative control. `isColour` is the one piece of judgement
 * here that is not measured against a real build, so it is measured against a
 * table instead, in both directions. The first three invalid rows are the shapes
 * that actually shipped: `hsl()` over a hex is the token fix defect, and the two
 * malformed hexes are what "an invalid value that is still a literal" means.
 */
describe('the colour validator judges both ways', () => {
  const VALID = [
    '#fff',
    '#fbf8f1',
    '#a3c398ff',
    'white',
    'transparent',
    'rgb(62 92 56)',
    'rgba(62, 92, 56, 0.5)',
    'hsl(105 24% 29%)',
    'oklch(0.45 0.06 140)',
    'color-mix(in oklab, #a3c398 92%, white)',
    'color-mix(in srgb, #3e5c38 94%, black)',
    'color-mix(in oklab, color-mix(in srgb, #fff 50%, black) 50%, #000)',
  ]

  const INVALID = [
    'hsl(#e5e7eb)',
    'hsl(#8a8072)',
    'rgb(#fff)',
    '#ff',
    '#gggggg',
    'bananas',
    'var(--border)',
    'color-mix(in oklab, bananas 92%, white)',
    'color-mix(#fff, #000)',
    '0.5rem',
    '',
  ]

  it.each(VALID)('accepts %s', (value) => {
    expect(isColour(value)).toBe(true)
  })

  it.each(INVALID)('rejects %s', (value) => {
    expect(isColour(value)).toBe(false)
  })
})
