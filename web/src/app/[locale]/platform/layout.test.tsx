import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { createTranslator } from 'next-intl'
import { expected, renderWithProviders } from '@/shared/testing/render'
import PlatformLayout from './layout'
import viMessages from '../../../../messages/vi.json'
import zhMessages from '../../../../messages/zh.json'

/**
 * #194: the platform banner was English for every locale. The layout is an async server
 * component behind `guardPlatformRoute`, so the case mocks the guard, awaits the element the
 * layout returns, and renders it.
 *
 * `getTranslations` is replaced by next-intl's own `createTranslator` over the real locale file
 * for the locale the layout asks for, which is what the server version does with the request
 * config. A layout that asked for the wrong locale would read another locale's banner.
 *
 * Negative control, 2026-10-06, with the key in all four locale files and the layout still
 * holding the literal: the vi case failed with `Unable to find an element with the text: Quản
 * trị nền tảng – chỉ dành cho quản trị viên cấp cao`, with the English sentence in the printed DOM.
 */

const MESSAGES = { vi: viMessages, zh: zhMessages } as const

vi.mock('@/features/auth/index.server', () => ({ guardPlatformRoute: vi.fn() }))
vi.mock('next-intl/server', () => ({
  getTranslations: async ({
    locale,
    namespace,
  }: {
    locale: keyof typeof MESSAGES
    namespace: string
  }) => createTranslator({ locale, messages: MESSAGES[locale], namespace: namespace as never }),
}))

async function renderLayout(locale: keyof typeof MESSAGES) {
  const element = await PlatformLayout({
    children: <p>page</p>,
    params: Promise.resolve({ locale }),
  })
  renderWithProviders(element, { locale, messages: MESSAGES[locale] })
}

describe('the platform banner', () => {
  it('reads in Vietnamese under the vi locale', async () => {
    await renderLayout('vi')

    expect(screen.getByText(expected(viMessages.platform.area_notice))).toBeInTheDocument()
  })

  it('reads in Chinese under the zh locale', async () => {
    await renderLayout('zh')

    expect(screen.getByText(expected(zhMessages.platform.area_notice))).toBeInTheDocument()
  })
})
