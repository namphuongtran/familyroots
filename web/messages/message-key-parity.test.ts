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
 * **Why this only checks three namespaces, not the whole file.** The obvious, stronger test
 * is "all four locale files carry the same key set, full stop." Measured 2026-08-22 while
 * building this test: they do not, and not because of anything S-062 touched. `zh.json` and
 * `fr.json` are each missing 61 keys that `vi.json` and `en.json` both carry, across five
 * namespaces that predate this seed and that S-062's sources never name: `relationship`,
 * `document`, `event`, `common`, and `auth` (for example `relationship.spouse`,
 * `document.upload`, `event.birthday`, `common.confirm`, `auth.join_subtitle` — 61 in total,
 * confirmed identical between `zh` and `fr`). Asserting global parity here would fail on that
 * pre-existing drift on the very first run, for a reason this seed did not create and is not
 * sized to fix — repairing five namespaces of missing Chinese and French copy is translation
 * work, not a message-key deletion. Recording it as passing by silently excluding it would be
 * the same defect this rule exists to catch, so it is named here instead, for whoever opens the
 * seed that fixes it. What this test does check is real: the three namespaces S-062 edited, plus
 * confirmation that `relationship_form` (the namespace S-062 removed outright) is gone from
 * every locale. A key deleted from only one of the four files inside `member`, `member_form`,
 * or `members` fails this test today, which is the property S-062's own change needs guarded.
 */

const LOCALES = ['vi', 'en', 'zh', 'fr'] as const
const TOUCHED_NAMESPACES = ['member', 'member_form', 'members'] as const
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

describe('locale files carry the same key set, in the namespaces S-062 changed', () => {
  const messagesByLocale = Object.fromEntries(LOCALES.map((l) => [l, loadMessages(l)])) as Record<
    (typeof LOCALES)[number],
    Record<string, unknown>
  >

  it.each(TOUCHED_NAMESPACES)('%s has an identical key set across vi, en, zh, and fr', (ns) => {
    const keySets = LOCALES.map((locale) => {
      const namespace = messagesByLocale[locale][ns]
      expect(namespace, `${locale}.json is missing the "${ns}" namespace`).toBeTypeOf('object')
      return new Set(flattenKeys(namespace as Record<string, unknown>))
    })

    const [reference, ...rest] = keySets
    LOCALES.slice(1).forEach((locale, i) => {
      const other = rest[i]
      const missingFromOther = [...reference].filter((k) => !other.has(k))
      const extraInOther = [...other].filter((k) => !reference.has(k))
      expect(missingFromOther, `${ns}: keys in vi.json but missing from ${locale}.json`).toEqual([])
      expect(extraInOther, `${ns}: keys in ${locale}.json but not in vi.json`).toEqual([])
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
