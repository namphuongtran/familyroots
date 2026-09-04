/**
 * The clan code — the `slug` the backend stores — and how a clan name becomes one.
 *
 * The clan-code spec. ADR-057 kept the typed clan code as the **secondary** join path, so this
 * value is both the clan's URL identifier and the string a relative may be asked to
 * type. Spec § 7.1b
 * (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:862-864`) asks for it
 * to be "auto-suggested, slugified live from the name, editable".
 *
 * This file is in `src/domain` because it is pure: no React, no fetch, no locale. It
 * imports nothing at all, which `pnpm depcruise`'s `domain-is-pure` and
 * `domain-imports-only-domain` rules both require.
 */

/**
 * Byte-identical to the backend's `_SLUG_PATTERN`, declared at
 * `backend/app/schemas/auth.py:11`. ADR-057 says the pattern is reused, not re-written,
 * and TypeScript cannot import a Python string — so `clan-code.test.ts` reads that file
 * and asserts the two sources are the same text. That is the reuse, made checkable.
 */
export const CLAN_CODE_PATTERN_SOURCE = '^[a-z0-9]+(?:-[a-z0-9]+)*$'

/** `clan_slug` is `Field(None, max_length=100, ...)` — `backend/app/schemas/auth.py:33,42`. */
export const CLAN_CODE_MAX_LENGTH = 100

/** The error code a taken code arrives as. `backend/app/application/auth/handlers.py:171,270`. */
export const CLAN_CODE_TAKEN_ERROR_CODE = 'auth.clan_slug_taken'

/**
 * The error code a join code no clan carries arrives as, raised by
 * `_resolve_join_target` at `backend/app/application/auth/handlers.py:147` and documented
 * at `docs/contracts/error-codes.md:114` as a 404.
 *
 * It is **not** namespaced under `auth.`, unlike `CLAN_CODE_TAKEN_ERROR_CODE` above, and
 * the difference is load-bearing rather than an oversight: the same code answers clan
 * detail and the platform-admin routes, so its backend `message` is deliberately generic
 * ("Không tìm thấy dòng họ", `backend/app/i18n/vi.json:4`). Spec § 7.1b asks the register
 * field for its own wording, so the register page renders `auth.clan_slug_not_found` from
 * `web/messages/*.json` and drops the backend message on this one branch. The join-code backend change's
 * commit `bc73f7c` says so in as many words: "the inline register-field wording spec
 * s7.1b asks for belongs to the web register form".
 */
export const CLAN_NOT_FOUND_ERROR_CODE = 'clan_not_found'

/**
 * Letters that Unicode NFD leaves whole, so a "normalise then drop the combining marks"
 * slugifier hands them to the `[a-z0-9]` filter, which deletes them.
 *
 * **This is the trap the whole file exists for.** Measured 2026-08-26 with Node 22:
 * `'Đ'.normalize('NFD')` is still the single code point U+0110, and `'đ'.normalize('NFD')`
 * is still U+0111 — a stroke letter has no canonical decomposition, unlike a letter that
 * carries a combining mark. So the naive pipeline turns `Đặng Đình` into `ang-inh`: two
 * letters gone, silently, from the identifier that goes in a URL and in the invite links
 * built from it. Mapping them **before** normalising is the fix.
 *
 * The rest of the table is the same defect in the other direction the product can reach:
 * `fr` is a shipped locale (`web/messages/fr.json`), and `Ø æ œ ß ł þ` and the Icelandic
 * eth `Ð` (U+00D0, a different code point from the Vietnamese `Đ` U+0110, and easy to
 * mistake for it) all survive NFD whole for the same reason. `clan-code.test.ts` asserts
 * that no entry here is dropped.
 *
 * Uppercase entries are listed too rather than lower-casing first, because two of them
 * expand to more than one letter and the case of the expansion has to be chosen here.
 */
const LETTERS_NFD_LEAVES_WHOLE: ReadonlyArray<readonly [string, string]> = [
  ['Đ', 'D'],
  ['đ', 'd'],
  ['Ð', 'D'],
  ['ð', 'd'],
  ['Ø', 'O'],
  ['ø', 'o'],
  ['Æ', 'AE'],
  ['æ', 'ae'],
  ['Œ', 'OE'],
  ['œ', 'oe'],
  ['ß', 'ss'],
  ['Ł', 'L'],
  ['ł', 'l'],
  ['Þ', 'TH'],
  ['þ', 'th'],
]

/**
 * Combining marks to drop after NFD.
 *
 * `\p{M}` would read better, but `web/tsconfig.json` targets ES2017 and a Unicode
 * property escape is ES2018, so this range is used instead. It is not a compromise for
 * Vietnamese: every mark the language uses decomposes into this block, verified
 * 2026-08-26 by printing the NFD code points of the full tone-and-diacritic set —
 * combining grave U+0300, acute U+0301, tilde U+0303, breve U+0306, circumflex U+0302,
 * hook above U+0309, horn U+031B, and dot below U+0323.
 *
 * **The `ư`/`ơ` family needs no table entry, and it is worth saying why.** They look like
 * the `Đ` case and are not: `'ư'.normalize('NFD')` is U+0075 U+031B and `'ơ'` is U+006F
 * U+031B (measured 2026-08-26), so the horn is an ordinary combining mark this range
 * removes, leaving `u` and `o`. Nothing is dropped. `ườ` reads back as `uo`.
 */
const COMBINING_MARKS = /[\u0300-\u036f]/g

/** Anything left that a slug cannot contain becomes a separator. */
const NOT_SLUG_SAFE = /[^a-z0-9]+/g

const LEADING_OR_TRAILING_HYPHENS = /^-+|-+$/g

/** A code the person (or this file) already suffixed, so a second suggestion counts up. */
const TRAILING_COUNTER = /^(.+)-(\d+)$/

/**
 * Suggest a clan code for a clan name.
 *
 * Returns `''` when the name yields nothing a slug can hold — an all-Chinese name, for
 * one, which is reachable because `zh` is a shipped locale. An empty suggestion is the
 * honest answer: the field stays empty and the person types their own code, which is
 * better than offering a code built from the few characters that happened to survive.
 */
export function suggestClanCode(clanName: string): string {
  let mapped = clanName
  for (const [letter, replacement] of LETTERS_NFD_LEAVES_WHOLE) {
    mapped = mapped.split(letter).join(replacement)
  }

  return (
    mapped
      .normalize('NFD')
      .replace(COMBINING_MARKS, '')
      .toLowerCase()
      .replace(NOT_SLUG_SAFE, '-')
      .replace(LEADING_OR_TRAILING_HYPHENS, '')
      .slice(0, CLAN_CODE_MAX_LENGTH)
      // The slice can land mid-separator, and a trailing hyphen fails the pattern.
      .replace(LEADING_OR_TRAILING_HYPHENS, '')
  )
}

/** Whether a code is one the backend will accept. */
export function isValidClanCode(code: string): boolean {
  return (
    code.length > 0 &&
    code.length <= CLAN_CODE_MAX_LENGTH &&
    new RegExp(CLAN_CODE_PATTERN_SOURCE).test(code)
  )
}

/**
 * The alternative offered when a code is already taken, which spec § 7.1b requires
 * beside the inline error.
 *
 * Counting up rather than picking a random suffix, so that a person who takes the
 * suggestion and loses the race again is offered the next number rather than the same
 * one. Deterministic, which is also why a test can pin it. Returns `''` for an empty or
 * invalid code: there is nothing to count up from, and offering `-2` on a code the
 * backend would reject anyway helps nobody.
 */
export function suggestAlternativeClanCode(code: string): string {
  if (!isValidClanCode(code)) {
    return ''
  }

  const counted = TRAILING_COUNTER.exec(code)
  const base = counted ? counted[1] : code
  const next = counted ? Number(counted[2]) + 1 : 2
  const suffix = `-${next}`

  return `${base.slice(0, CLAN_CODE_MAX_LENGTH - suffix.length).replace(LEADING_OR_TRAILING_HYPHENS, '')}${suffix}`
}
