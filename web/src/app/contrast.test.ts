import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/**
 * Seed S-003. Spec § 1 rule 6 says the contrast floor "is enforced at the token
 * level, so a designer cannot accidentally ship an unreadable pairing". Nothing
 * enforced it, and four pairs shipped below AA. This test is the enforcement.
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
 *
 * `border` is deliberately absent from the table below. It measured 1.13 on
 * `background` on 2026-08-13 and that is not a defect: the `*` rule in
 * `globals.css` applies `border-border` to every element, so it is decorative,
 * and WCAG 1.4.11 exempts a decoration. `input` carries an input's boundary and
 * is held to 3:1 here. Spec § 2.8.1 F reasons the same way.
 *
 * If a case fails, move the token value, not the threshold.
 */
const AA_NORMAL_TEXT = 4.5
const NON_TEXT_BOUNDARY = 3

const css = readFileSync(new URL('globals.css', import.meta.url), 'utf8')

const declared = new Map<string, string>()
for (const [, name, hex] of css.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
  declared.set(name, hex.toLowerCase())
}

/**
 * Throws rather than returning undefined. A renamed token must fail loudly: a
 * table of pairs that silently resolves to nothing passes every assertion.
 */
const token = (name: string): string => {
  const hex = declared.get(name)
  if (hex === undefined) {
    throw new Error(
      `globals.css declares no --color-${name}. Either the token was renamed, or the ` +
        `@theme block no longer holds a literal hex value. This table cannot check what it ` +
        `cannot read.`,
    )
  }
  return hex
}

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

describe('every token pair the app can compose clears WCAG AA', () => {
  it.each(CASES)('$text on $on clears $floor:1', ({ text, on, floor }) => {
    const ratio = contrast(token(text), token(on))

    expect(
      Number(ratio.toFixed(2)),
      `${text} ${token(text)} on ${on} ${token(on)} measured ${ratio.toFixed(2)}:1`,
    ).toBeGreaterThanOrEqual(floor)
  })

  it('read the seventeen semantic tokens, not zero of them', () => {
    // Guards the regex above. A parse that matches nothing makes every case
    // throw, but a parse that matches only the primary ramp would not.
    expect(declared.size).toBeGreaterThanOrEqual(17)
  })
})

/**
 * The hover fills are the one part of the palette this table cannot measure: a
 * `color-mix` is not a hex, so `declared` never sees them. Nothing else would
 * notice if they were deleted either — Tailwind simply stops generating
 * `bg-primary-hover`, the class becomes inert, and the button loses its hover
 * state silently. So the derivation is asserted here instead of the value.
 *
 * Spec § 4.1 line 582: hover is the fill darkened 6%. Keep these derived from
 * the base token. A literal hex here is a second value to keep in sync, which
 * is the defect ADR-041 § 5 was written to avoid.
 */
describe('the hover fills stay derived from the fill they darken', () => {
  const derived = new Map<string, string>()
  for (const [, name, value] of css.matchAll(
    /--color-([a-z0-9-]+):\s*(color-mix\([^;]+\))\s*;/g,
  )) {
    derived.set(name, value)
  }

  it.each([
    ['primary-hover', 'primary'],
    ['primary-container-hover', 'primary-container'],
  ])('%s mixes black into %s', (hover, base) => {
    const value = derived.get(hover)

    expect(value, `globals.css declares no --color-${hover}`).toBeDefined()
    expect(value).toContain(`var(--color-${base})`)
    expect(value).toContain('black')
  })
})
