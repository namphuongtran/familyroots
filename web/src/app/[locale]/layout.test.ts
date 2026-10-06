import { describe, expect, it, vi } from 'vitest'
import { createTranslator } from 'next-intl'
import { expected } from '@/shared/testing/render'
import { generateMetadata } from './layout'
import enMessages from '../../../messages/en.json'
import viMessages from '../../../messages/vi.json'

/**
 * #197: the document title and description were one static Vietnamese pair, so an English,
 * Chinese or French reader's tab and search snippet read Vietnamese. `getTranslations` is
 * next-intl's own `createTranslator` over the real locale file the layout asks for, as in
 * `platform/layout.test.tsx`, so a layout that asked for the wrong locale reads another locale's
 * words.
 *
 * Negative control, 2026-10-06, with the keys in all four locale files and `generateMetadata`
 * returning the static `metadata` it replaces: the en case failed with
 * `expected 'Nền tảng quản lý gia phả dòng họ Việt…' to be 'A platform for managing
 * Vietnamese cl…'`.
 */

const MESSAGES = { vi: viMessages, en: enMessages } as const

vi.mock('next-intl/server', () => ({
  getTranslations: async ({
    locale,
    namespace,
  }: {
    locale: keyof typeof MESSAGES
    namespace: string
  }) => createTranslator({ locale, messages: MESSAGES[locale], namespace: namespace as never }),
}))

describe('the [locale] layout metadata follows the locale', () => {
  it('reads in English under en', async () => {
    const metadata = await generateMetadata({ params: Promise.resolve({ locale: 'en' }) })

    expect(metadata.description).toBe(expected(enMessages.metadata.description))
    expect(metadata.title).toBe(`FamilyRoots – ${expected(enMessages.metadata.tagline)}`)
  })

  // Literal on purpose: #197 asks that the vi values stay exactly what the static pair said.
  it('keeps the Vietnamese pair it always had under vi', async () => {
    const metadata = await generateMetadata({ params: Promise.resolve({ locale: 'vi' }) })

    expect(metadata.title).toBe('FamilyRoots – Gia phả Việt Nam')
    expect(metadata.description).toBe('Nền tảng quản lý gia phả dòng họ Việt Nam')
  })
})
