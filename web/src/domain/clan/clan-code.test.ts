import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  CLAN_CODE_MAX_LENGTH,
  CLAN_CODE_PATTERN_SOURCE,
  isValidClanCode,
  suggestAlternativeClanCode,
  suggestClanCode,
} from './clan-code'

/**
 * the clan-code spec. These assertions are about what `suggestClanCode` **returns**, not about
 * what it is configured with — but on their own they still do not establish the seed's
 * end state, which is about the value in the code field on the register screen. That is
 * `src/app/[locale]/(auth)/register/page.test.tsx` (jsdom) and
 * `e2e/register-clan-code.spec.ts` (a real browser). This file is the layer below.
 */

/** The 29 letters of the Vietnamese alphabet, in dictionary order, lower case. */
const VIETNAMESE_ALPHABET = 'aăâbcdđeêghiklmnoôơpqrstuưvxy'

/** Every vowel that carries tone marks, with its five tones after the plain form. */
const TONE_ROWS: ReadonlyArray<readonly [string, string]> = [
  ['a', 'aàáảãạ'],
  ['ă', 'ăằắẳẵặ'],
  ['â', 'âầấẩẫậ'],
  ['e', 'eèéẻẽẹ'],
  ['ê', 'êềếểễệ'],
  ['i', 'iìíỉĩị'],
  ['o', 'oòóỏõọ'],
  ['ô', 'ôồốổỗộ'],
  ['ơ', 'ơờớởỡợ'],
  ['u', 'uùúủũụ'],
  ['ư', 'ưừứửữự'],
  ['y', 'yỳýỷỹỵ'],
]

describe('suggestClanCode transliterates a Vietnamese clan name', () => {
  it('turns "Trần Gia" into "tran-gia", which is the case the seed names', () => {
    expect(suggestClanCode('Trần Gia')).toBe('tran-gia')
  })

  it('keeps the D of Đ, which a naive NFD strip deletes', () => {
    // The defect this whole module exists for: `'Đ'.normalize('NFD')` is still U+0110,
    // so a mark-stripping slugifier hands it to the `[a-z0-9]` filter, which drops it
    // and yields "ang-inh". Two letters gone from a URL identifier, silently.
    expect(suggestClanCode('Đặng Đình')).toBe('dang-dinh')
    expect(suggestClanCode('Đặng Đình')).not.toBe('ang-inh')
  })

  it('reads the ư/ơ family back as u and o rather than dropping them', () => {
    // These look like the Đ case and are not: the horn is a combining mark (U+031B),
    // so NFD does decompose them. Asserted so a later reader does not "fix" it by
    // adding a table entry that would then double-map.
    expect(suggestClanCode('Hữu Thọ')).toBe('huu-tho')
    expect(suggestClanCode('Nguyễn Hữu Thanh Oai')).toBe('nguyen-huu-thanh-oai')
  })

  it('drops no letter of the Vietnamese alphabet', () => {
    // The outcome that matters is one ASCII letter out for one Vietnamese letter in.
    // Counting, rather than spot-checking, is what makes a newly-dropped letter fail
    // this test instead of slipping past it.
    const slug = suggestClanCode(VIETNAMESE_ALPHABET)
    expect([...VIETNAMESE_ALPHABET]).toHaveLength(29)
    expect(slug).toBe('aaabcddeeghiklmnooopqrstuuvxy')
    expect([...slug]).toHaveLength(29)
  })

  it.each(TONE_ROWS)('collapses every tone of %s onto one base letter', (base, row) => {
    const expected = suggestClanCode(base).repeat([...row].length)
    expect(suggestClanCode(row)).toBe(expected)
    expect([...suggestClanCode(row)]).toHaveLength([...row].length)
  })

  it('drops no stroke or ligature letter that NFD leaves whole', () => {
    // `fr` is a shipped locale, so these are reachable. `Ð` (U+00D0) is the Icelandic
    // eth, a different code point from the Vietnamese `Đ` (U+0110) and easy to mistake
    // for it — both are asserted.
    expect(suggestClanCode('Ðông')).toBe('dong')
    expect(suggestClanCode('Øst')).toBe('ost')
    expect(suggestClanCode('Ærø')).toBe('aero')
    expect(suggestClanCode('Œuvre')).toBe('oeuvre')
    expect(suggestClanCode('Straße')).toBe('strasse')
    expect(suggestClanCode('Łódź')).toBe('lodz')
    expect(suggestClanCode('Þór')).toBe('thor')
  })
})

describe('suggestClanCode produces a code the backend will accept, or nothing at all', () => {
  const NAMES = [
    'Trần Gia',
    'Đặng Đình',
    '  Nguyễn   Hữu  Thanh Oai!!  ',
    'Họ Lê — chi Quảng Ngãi (1802)',
    'a'.repeat(CLAN_CODE_MAX_LENGTH + 20),
    'a'.repeat(CLAN_CODE_MAX_LENGTH - 1) + ' b',
    'Straße 12',
  ]

  it.each(NAMES)('"%s" yields a code matching the backend pattern', (name) => {
    const slug = suggestClanCode(name)
    expect(slug).not.toBe('')
    expect(isValidClanCode(slug)).toBe(true)
    expect(slug.length).toBeLessThanOrEqual(CLAN_CODE_MAX_LENGTH)
  })

  it('collapses runs of punctuation and spaces into single hyphens with no edges', () => {
    expect(suggestClanCode('  Trần   Gia!!  ')).toBe('tran-gia')
    expect(suggestClanCode('---Lê---')).toBe('le')
  })

  it('truncates to the backend max_length without leaving a trailing hyphen', () => {
    const overLong = suggestClanCode('a'.repeat(CLAN_CODE_MAX_LENGTH - 1) + ' b')
    expect(overLong).toHaveLength(CLAN_CODE_MAX_LENGTH - 1)
    expect(overLong.endsWith('-')).toBe(false)
    expect(isValidClanCode(overLong)).toBe(true)
  })

  it('returns an empty string rather than a scrap when nothing transliterates', () => {
    // `zh` is a shipped locale, so an all-Chinese clan name is reachable. An empty
    // suggestion leaves the field empty for the person to fill, which is honest; a
    // code built from whatever happened to survive would not be.
    expect(suggestClanCode('家族')).toBe('')
    expect(suggestClanCode('')).toBe('')
    expect(suggestClanCode('   ')).toBe('')
  })
})

describe('isValidClanCode agrees with the backend pattern', () => {
  it.each(['tran-gia', 'le', 'nguyen-huu-thanh-oai', 'a1', '2026'])('accepts "%s"', (code) => {
    expect(isValidClanCode(code)).toBe(true)
  })

  it.each(['', '-le', 'le-', 'Tran-Gia', 'tran gia', 'tran--gia', 'trần', 'a'.repeat(101)])(
    'rejects "%s"',
    (code) => {
      expect(isValidClanCode(code)).toBe(false)
    },
  )
})

describe('suggestAlternativeClanCode counts up', () => {
  it('appends -2 to a code with no counter', () => {
    expect(suggestAlternativeClanCode('tran-gia')).toBe('tran-gia-2')
  })

  it('increments a counter it already put there, so a second collision moves on', () => {
    expect(suggestAlternativeClanCode('tran-gia-2')).toBe('tran-gia-3')
    expect(suggestAlternativeClanCode('tran-gia-9')).toBe('tran-gia-10')
  })

  it('stays inside max_length by trimming the base, not the counter', () => {
    const alternative = suggestAlternativeClanCode('a'.repeat(CLAN_CODE_MAX_LENGTH))
    expect(alternative).toHaveLength(CLAN_CODE_MAX_LENGTH)
    expect(alternative.endsWith('-2')).toBe(true)
    expect(isValidClanCode(alternative)).toBe(true)
  })

  it('offers nothing for a code the backend would reject anyway', () => {
    expect(suggestAlternativeClanCode('')).toBe('')
    expect(suggestAlternativeClanCode('Tran Gia')).toBe('')
  })
})

describe('the pattern is the backend pattern, not a second copy of the same idea', () => {
  /**
   * ADR-057: "`_SLUG_PATTERN` is reused, not re-written. A second pattern for the same
   * shape is a second place to be wrong." TypeScript cannot import a Python string, so
   * this reads the declaration and compares the text. `web-ci.yml` checks out the whole
   * repository (`actions/checkout@v4` at the root, and its `contract-drift` job runs
   * with `working-directory: backend`), so `backend/` is present when this runs in CI.
   */
  it('matches _SLUG_PATTERN in backend/app/schemas/auth.py character for character', () => {
    const schemaPath = join(__dirname, '../../../../backend/app/schemas/auth.py')
    const source = readFileSync(schemaPath, 'utf-8')
    const declaration = /^_SLUG_PATTERN = r"(.+)"$/m.exec(source)

    expect(declaration, `no _SLUG_PATTERN declaration found in ${schemaPath}`).not.toBeNull()
    expect(declaration![1]).toBe(CLAN_CODE_PATTERN_SOURCE)
  })

  it('reads the same max_length the backend declares for clan_slug', () => {
    const schemaPath = join(__dirname, '../../../../backend/app/schemas/auth.py')
    const source = readFileSync(schemaPath, 'utf-8')
    const declaration = /clan_slug: str \| None = Field\(None, max_length=(\d+),/.exec(source)

    expect(declaration, `no clan_slug Field found in ${schemaPath}`).not.toBeNull()
    expect(Number(declaration![1])).toBe(CLAN_CODE_MAX_LENGTH)
  })
})
