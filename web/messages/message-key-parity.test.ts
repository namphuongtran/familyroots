import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Seed S-062. S-033 deleted six legacy person components and, with them, every caller of
 * 44-by-the-coordinator's-count message keys across `member`, `member_form`, `members`, and the
 * wholly-dead `relationship_form` namespace. S-033 was fenced out of `web/messages/*.json` for
 * that batch, so it reported the question as "unconfirmed, not observed" rather than "none" —
 * this file is the "none" a later reader can trust, because it runs.
 *
 * This file lives outside `web/src` on purpose: seed S-038 is sweeping `web/src` the same batch,
 * and a test file under `src/` would conflict with it. `vitest.config.mts`'s `unit` project
 * include was widened to `messages/**\/*.test.ts` so this still runs under `pnpm test:unit`,
 * which is in the full gate (`web/CLAUDE.md`).
 *
 * **Widened to the whole file by seed S-066 (2026-08-22).** S-062 scoped this test to three
 * namespaces because, at the time, `zh.json` and `fr.json` were each missing 61 keys that
 * `vi.json` and `en.json` both carried, across five namespaces this seed never touched:
 * `relationship`, `document`, `event`, `common`, and `auth`. That drift predated S-062 and a
 * global assertion would have failed on it immediately, for a reason S-062 was not sized to fix.
 * S-066 is that fix: it added the 61 missing keys, with real Chinese and French translations, not
 * copies of the English or Vietnamese values. With the drift gone, the whole-file assertion below
 * is real rather than aspirational — **watch it fail before the keys land, and pass after**, per
 * `.claude/rules/seeds.md`'s "a test pins an outcome, not a setting". Do not narrow this back down
 * to a namespace subset; if a future drift reintroduces a gap, that is the defect to fix, not the
 * test.
 */

const LOCALES = ['vi', 'en', 'zh', 'fr'] as const
const REMOVED_NAMESPACE = 'relationship_form'

function loadMessages(locale: (typeof LOCALES)[number]): Record<string, unknown> {
  const raw = readFileSync(join(__dirname, `${locale}.json`), 'utf-8')
  return JSON.parse(raw) as Record<string, unknown>
}

/** Flattens a namespace object to dot-paths, so a nested table (`relationship_form.status.*`,
 * were it still here) compares the same way a flat one does. */
function flattenKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const out: string[] = []
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      out.push(...flattenKeys(value as Record<string, unknown>, path))
    } else {
      out.push(path)
    }
  }
  return out
}

describe('locale files carry the same key set, across the whole file', () => {
  const messagesByLocale = Object.fromEntries(LOCALES.map((l) => [l, loadMessages(l)])) as Record<
    (typeof LOCALES)[number],
    Record<string, unknown>
  >

  it('every locale has an identical key set to vi.json', () => {
    const keySets = LOCALES.map((locale) => new Set(flattenKeys(messagesByLocale[locale])))

    const [reference, ...rest] = keySets
    LOCALES.slice(1).forEach((locale, i) => {
      const other = rest[i]
      const missingFromOther = [...reference].filter((k) => !other.has(k))
      const extraInOther = [...other].filter((k) => !reference.has(k))
      expect(missingFromOther, `keys in vi.json but missing from ${locale}.json`).toEqual([])
      expect(extraInOther, `keys in ${locale}.json but not in vi.json`).toEqual([])
    })
  })

  it(`"${REMOVED_NAMESPACE}" is gone from every locale`, () => {
    for (const locale of LOCALES) {
      expect(
        Object.prototype.hasOwnProperty.call(messagesByLocale[locale], REMOVED_NAMESPACE),
        `${locale}.json still declares the "${REMOVED_NAMESPACE}" namespace`,
      ).toBe(false)
    }
  })
})
