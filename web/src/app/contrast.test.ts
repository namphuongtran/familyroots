import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * Seed S-003 opened this file. Spec § 1 rule 6 says the contrast floor "is
 * enforced at the token level, so a designer cannot accidentally ship an
 * unreadable pairing". Nothing enforced it, and four pairs shipped below AA.
 * This test is the enforcement.
 *
 * Seed S-006 ran the same table over the dark palette, and had to change how the
 * values are read to do it. **Read the next paragraph before editing the parser.**
 *
 * It reads the real stylesheet rather than a copy of the values, because a copy
 * is a second place to be wrong. It computes the ratios rather than quoting
 * them, because a ratio is a measurement and a number typed into a file is not.
 *
 * It reads the source rather than a browser on purpose, and that is not the lazy
 * choice. Tailwind v4 emits an `@theme` variable only when some generated rule
 * references it, so a token no class uses today is absent from the built CSS and
 * a `var(--color-x)` probe returns the inherited colour instead. Measured
 * 2026-08-13, that is fifteen of the seventeen. So a browser cannot tell "no
 * class asks for it yet" apart from "the declaration was dropped", while the
 * stylesheet holds the value unconditionally. See `.claude/rules/tailwind.md` § 2.
 * `web/e2e/dark-theme.spec.ts` covers the one question a browser answers better,
 * which is whether the override reaches a real screen.
 *
 * `border` is deliberately absent from the table below. It measured 1.13 on
 * `background` on 2026-08-13 and that is not a defect: the `*` rule in
 * `globals.css` applies `border-border` to every element, so it is decorative,
 * and WCAG 1.4.11 exempts a decoration. `input` carries an input's boundary and
 * is held to 3:1 here. Spec § 2.8.1 F reasons the same way. The dark value is
 * 1.11 to 1.29 across the three grounds, measured 2026-08-21, so the rule holds
 * in both themes.
 *
 * If a case fails, move the token value, not the threshold.
 */
const AA_NORMAL_TEXT = 4.5
const NON_TEXT_BOUNDARY = 3

/**
 * Comments are stripped before anything is parsed, and that is load-bearing
 * rather than tidy. `globals.css` explains at length *which* dark mechanisms
 * were rejected, so it names the class selector and the `data-theme` attribute
 * in prose. The mechanism cases below look for exactly those strings. Reading
 * the raw file would make the checker forbid the explanation, and the fix for
 * that is a better checker, not a worse comment. A mention is not a mechanism.
 *
 * Stripping also removes a fragility the scoped read would otherwise carry: the
 * `@theme` comments quote hex values and token names, and a parser that reads
 * them is one reworded sentence away from measuring a colour no rule declares.
 * Replaced with a newline rather than nothing, so a comment between two
 * declarations cannot splice them together.
 */
const css = readFileSync(new URL('globals.css', import.meta.url), 'utf8').replace(
  /\/\*[\s\S]*?\*\//g,
  '\n',
)

/**
 * Returns the body of the block that `opener` opens, found by counting braces.
 *
 * **Why a brace walk and not a regex, added 2026-08-21 by seed S-006.** Until
 * S-006 this file matched `--color-x: #hex;` over the whole stylesheet. That was
 * correct only while one scope declared colours. Once a second scope declares
 * `--color-background`, a file-wide match keeps whichever came last, so the
 * *light* table starts measuring the *dark* palette.
 *
 * **And it does not fail when that happens.** S-006 planted exactly that defect
 * on 2026-08-21 — `hexTokens(css)` in place of `hexTokens(LIGHT_SCOPE)` — and all
 * 156 cases still passed, because each palette is internally consistent, so
 * dark-on-dark clears AA just as light-on-light does. A silent pass is worse than
 * the failure this comment first claimed, and no reader would have caught it. The
 * `two different palettes` case further down is the gate for it: it is the only
 * thing standing between a scoped read and a table that measures the wrong theme
 * twice. A brace walk is needed rather than a lazy `{([^}]*)}` because `@theme`
 * contains nested `@keyframes` blocks.
 */
const blockBody = (source: string, opener: string): string => {
  const at = source.indexOf(opener)
  if (at === -1) {
    throw new Error(
      `globals.css holds no \`${opener}\` block. This table cannot check what it cannot ` +
        `read, so a missing scope is a failure rather than an empty pass.`,
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
  throw new Error(`\`${opener}\` in globals.css is never closed.`)
}

/**
 * The two colour scopes. `prefers-color-scheme` is the one dark mechanism this
 * app has, decided by ADR-045 and seed S-006; the class variant and the
 * `data-theme` selector spec § 2.8 also named are absent, and the block below
 * asserts that they stay absent.
 */
const LIGHT_SCOPE = blockBody(css, '@theme {')
const DARK_SCOPE = blockBody(css, '@media (prefers-color-scheme: dark) {')

const hexTokens = (scope: string): Map<string, string> => {
  const found = new Map<string, string>()
  for (const [, name, hex] of scope.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    found.set(name, hex.toLowerCase())
  }
  return found
}

const LIGHT = hexTokens(LIGHT_SCOPE)
const DARK_OVERRIDES = hexTokens(DARK_SCOPE)

/**
 * Dark redefines only the `--color-*` group it names, so what a dark screen
 * actually resolves is light overlaid by those. Modelling the cascade rather
 * than assuming a full second palette is what makes an unoverridden token show
 * up as a real failure instead of a missing key.
 */
const DARK = new Map([...LIGHT, ...DARK_OVERRIDES])

/** WCAG 2.1 relative luminance, one channel. */
const channel = (eightBit: number): number => {
  const unit = eightBit / 255
  return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4
}

const luminance = (hex: string): number => {
  const [r, g, b] = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16))
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

const contrast = (a: string, b: string): number => {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * Throws rather than returning undefined. A renamed token must fail loudly: a
 * table of pairs that silently resolves to nothing passes every assertion.
 */
const reader =
  (theme: string, tokens: Map<string, string>) =>
  (name: string): string => {
    const hex = tokens.get(name)
    if (hex === undefined) {
      throw new Error(
        `the ${theme} scope of globals.css declares no --color-${name}. Either the token was ` +
          `renamed, or the scope no longer holds a literal hex value. This table cannot check ` +
          `what it cannot read.`,
      )
    }
    return hex
  }

/**
 * Every ground a screen can paint under text today. `cream` used to be here
 * because `body` painted it while the semantic token called the page
 * `background`, and a foreground had to clear both. ADR-041 § 3 ended that on
 * 2026-08-14: the page is one value under one name, `background` #fbf8f1, and
 * the bare `--color-cream` is gone. Seed S-005 removed the fourth entry here in
 * the same change, which is why `token('cream')` now throws.
 */
const GROUNDS = ['card', 'background', 'muted'] as const

type Case = { readonly text: string; readonly on: string; readonly floor: number }

const everyGround = (text: string, floor: number): Case[] =>
  GROUNDS.map((ground) => ({ text, on: ground, floor }))

const CASES: readonly Case[] = [
  // Body and helper text, against every ground it can land on. The second row
  // is the one S-003 was written for.
  ...everyGround('foreground', AA_NORMAL_TEXT),
  ...everyGround('muted-foreground', AA_NORMAL_TEXT),

  // Red error text, and coloured link/action text. `heritage` is the ceremonial
  // red (thủy tổ, giỗ), added with the family by seed S-005.
  ...everyGround('destructive', AA_NORMAL_TEXT),
  ...everyGround('primary', AA_NORMAL_TEXT),
  ...everyGround('heritage', AA_NORMAL_TEXT),

  // Positive/success state, added by ADR-055 (seed S-068) for the approve
  // action, the active/suspended badge, and a positive trend reading — each
  // paired against an already-tested `destructive` for its negative half.
  ...everyGround('success', AA_NORMAL_TEXT),

  // A label on a filled surface: the pair is fixed, so no ground sweep.
  //
  // `primary-container` and `heritage-container` appear only on the `on` side,
  // and that is deliberate (ADR-041, "Two rows must not be added"). They are
  // grounds, not boundaries. Sweeping them as foregrounds against the page
  // measures 1.25 and 1.20 (2026-08-14), and that failure would mean nothing:
  // WCAG 1.4.11
  // governs boundaries and meaningful graphics, not the ground colour of a
  // tonal card.
  { text: 'card-foreground', on: 'card', floor: AA_NORMAL_TEXT },
  { text: 'popover-foreground', on: 'popover', floor: AA_NORMAL_TEXT },
  { text: 'primary-foreground', on: 'primary', floor: AA_NORMAL_TEXT },
  { text: 'primary-container-foreground', on: 'primary-container', floor: AA_NORMAL_TEXT },
  { text: 'heritage-foreground', on: 'heritage', floor: AA_NORMAL_TEXT },
  { text: 'heritage-container-foreground', on: 'heritage-container', floor: AA_NORMAL_TEXT },
  { text: 'secondary-foreground', on: 'secondary', floor: AA_NORMAL_TEXT },
  { text: 'destructive-foreground', on: 'destructive', floor: AA_NORMAL_TEXT },
  { text: 'accent-foreground', on: 'accent', floor: AA_NORMAL_TEXT },

  // Boundaries a user needs to find the control. WCAG 1.4.11, so 3:1.
  ...everyGround('input', NON_TEXT_BOUNDARY),
  ...everyGround('ring', NON_TEXT_BOUNDARY),
]

const THEMES = [
  { theme: 'light', tokens: LIGHT },
  { theme: 'dark', tokens: DARK },
] as const

describe.each(THEMES)(
  'every token pair the app can compose clears WCAG AA in $theme',
  ({ theme, tokens }) => {
    const token = reader(theme, tokens)

    it.each(CASES)('$text on $on clears $floor:1', ({ text, on, floor }) => {
      const ratio = contrast(token(text), token(on))

      expect(
        Number(ratio.toFixed(2)),
        `${theme}: ${text} ${token(text)} on ${on} ${token(on)} measured ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(floor)
    })

    it('read the seventeen semantic tokens, not zero of them', () => {
      // Guards the parser above. A parse that matches nothing makes every case
      // throw, but a parse that matches only the primary ramp would not.
      expect(tokens.size).toBeGreaterThanOrEqual(17)
    })
  },
)

/**
 * Seed S-006's end state, stated as the thing that would be wrong without it: a
 * dark screen must not resolve a single one of these through a light value.
 * Without this case, forgetting an override is not a failure but a pass, because
 * `DARK` inherits from `LIGHT` exactly as the cascade does.
 */
describe('the dark scope covers the palette rather than inheriting it', () => {
  it('overrides every token this table measures', () => {
    const measured = [...new Set(CASES.flatMap(({ text, on }) => [text, on]))].sort()
    const missing = measured.filter((name) => !DARK_OVERRIDES.has(name))

    expect(missing, `the dark scope inherits these from light: ${missing.join(', ')}`).toEqual([])
  })

  /**
   * The gate for the planted defect described on `blockBody`. If the light read
   * ever goes file-wide again, `LIGHT` becomes `DARK` and every one of these
   * names lands in `same`, so the case fails loudly instead of the whole table
   * quietly grading dark against dark.
   *
   * It is a real invariant in its own right, not only a tripwire: an override
   * that restates the light value is either a typo or a token that did not need
   * overriding.
   */
  it('reads light and dark as two different palettes', () => {
    const same = [...DARK_OVERRIDES]
      .filter(([name, hex]) => LIGHT.get(name) === hex)
      .map(([name]) => name)

    expect(
      same,
      `the dark scope declares these with the light value, so either the light read is not ` +
        `scoped to @theme or the override is pointless: ${same.join(', ')}`,
    ).toEqual([])
  })
})

/**
 * Spec § 2.8 asks for two dark mechanisms and `globals.css:3` shipped a third,
 * the class-based `@custom-variant dark (&:is(.dark *))`. Three mechanisms for
 * one behaviour is the contradiction seed S-006 was written to settle, and
 * ADR-045 settles it: the media query wins, and it wins alone. The other two
 * need something to set a class or an attribute, and that something is the theme
 * switch this app does not have, so either one would have shipped a palette that
 * never activates.
 *
 * These three cases are what stops the other two coming back one component at a
 * time. Do not weaken them to make a component work; a component that needs a
 * class-based theme needs ADR-045 revisited first.
 */
describe('exactly one dark mechanism reaches the stylesheet', () => {
  it('switches on the colour-scheme media query, once', () => {
    expect(css.match(/@media \(prefers-color-scheme/g)).toHaveLength(1)
  })

  it('declares no class-based dark variant or selector', () => {
    expect(css).not.toContain('.dark')
  })

  it('declares no data-theme selector', () => {
    expect(css).not.toContain('data-theme')
  })
})

/**
 * The hover fills are the one part of the palette the table above cannot
 * measure: a `color-mix` is not a hex, so `hexTokens` never sees them. Nothing
 * else would notice if they were deleted either — Tailwind simply stops
 * generating `bg-primary-hover`, the class becomes inert, and the button loses
 * its hover state silently. So the derivation is asserted here instead of the
 * value.
 *
 * Spec § 4.1 line 582 gives both halves: hover is the fill "darkened 6% (light)
 * / lightened 8% (dark)". The dark half was missed until seed S-006, because
 * S-005 only needed the light one. The direction is the point: darkening an
 * already-light dark-theme fill moves it toward the ground rather than away from
 * it, so the two scopes mix opposite colours on purpose.
 */
describe('the hover fills stay derived from the fill they shift', () => {
  const mixesIn = (scope: string): Map<string, string> => {
    const derived = new Map<string, string>()
    for (const [, name, value] of scope.matchAll(
      /--color-([a-z0-9-]+):\s*(color-mix\([^;]+\))\s*;/g,
    )) {
      derived.set(name, value)
    }
    return derived
  }

  const HOVERS = [
    ['primary-hover', 'primary'],
    ['primary-container-hover', 'primary-container'],
  ] as const

  const LIGHT_HOVERS = mixesIn(LIGHT_SCOPE)
  const DARK_HOVERS = mixesIn(DARK_SCOPE)

  /**
   * Light reads its base through the token, which is what ADR-041 § 5 asks for:
   * one value, one place.
   */
  describe('in light, hover keeps 94% of the token and mixes black', () => {
    it.each(HOVERS)('%s darkens var(--color-%s)', (hover, base) => {
      const value = LIGHT_HOVERS.get(hover)

      expect(value, `the light scope of globals.css declares no --color-${hover}`).toBeDefined()
      expect(value).toContain(`var(--color-${base})`)
      expect(value).toContain('black')
      expect(value).toContain('94%')
    })
  })

  /**
   * Dark names its base as a **literal hex**, and that asymmetry is deliberate
   * and expensive to rediscover, so here is why.
   *
   * `var()` inside a `color-mix` is resolved statically by Lightning CSS when it
   * emits the pre-`color-mix()` sRGB fallback, and it resolves it against the
   * top-level `:root` rather than the scope the declaration sits in. Measured on
   * a production build, 2026-08-21: with `var(--color-primary)` in the dark
   * block, the emitted dark fallback was `#4d6948` — the *light* primary
   * lightened — and `primary-foreground` #12280d on it measures **2.57:1**, well
   * under AA. So a browser with `prefers-color-scheme` and without `color-mix()`
   * (roughly 2019 to 2023) got an unreadable label on hover, in dark, and every
   * source-level check passed over it.
   *
   * Naming the literal lets Lightning CSS resolve the whole mix at build time:
   * the same build then emits `--color-primary-hover: #aac8a0` with no
   * `@supports` fallback at all, and the label measures 8.60:1.
   *
   * The cost is a second copy of the hex, which is the defect ADR-041 § 5 warns
   * about. The two cases below are what stop it drifting: the literal in the mix
   * must equal the token it claims to shift. Do not replace them with a comment
   * asking the next reader to remember.
   */
  describe('in dark, hover keeps 92% of the fill and mixes white', () => {
    const MIX = /color-mix\(in oklab, (#[0-9a-f]{6}) (\d+)%, ([a-z]+)\)/

    it.each(HOVERS)('%s lightens the same hex --color-%s holds', (hover, base) => {
      const value = DARK_HOVERS.get(hover)

      expect(value, `the dark scope of globals.css declares no --color-${hover}`).toBeDefined()

      const mix = MIX.exec(value ?? '')
      expect(mix, `--color-${hover} is not a literal oklab mix: ${value}`).not.toBeNull()

      const [, literal, keeps, toward] = mix ?? []
      expect(keeps).toBe('92')
      expect(toward).toBe('white')
      expect(
        literal,
        `--color-${hover} shifts ${literal}, but the dark --color-${base} is ` +
          `${DARK_OVERRIDES.get(base)}. One of the two moved without the other.`,
      ).toBe(DARK_OVERRIDES.get(base))
    })
  })
})
