import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { LocaleSwitcher } from './LocaleSwitcher'
import viMessages from '../../../messages/vi.json'
import zhMessages from '../../../messages/zh.json'

/**
 * #194: the control a person uses to change language was named `Select language` in English for
 * every locale. Read through the accessible name, the way a screen reader computes it, because
 * an `aria-label` is never painted.
 *
 * Negative control, 2026-10-06, with the key in all four locale files and the component still
 * holding the literal: the vi case failed with
 *
 *     Expected element to have accessible name:
 *       Chọn ngôn ngữ
 *     Received:
 *       Select language
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/vi/dashboard',
}))

function renderSwitcher(locale: string, messages: AbstractIntlMessages) {
  renderWithProviders(<LocaleSwitcher />, { locale, messages })
  return screen.getByRole('combobox')
}

describe('LocaleSwitcher accessible name', () => {
  it('names the picker in Vietnamese under the vi locale', () => {
    expect(renderSwitcher('vi', viMessages)).toHaveAccessibleName(
      expected(viMessages.common.select_language),
    )
  })

  it('names the picker in Chinese under the zh locale', () => {
    expect(renderSwitcher('zh', zhMessages)).toHaveAccessibleName(
      expected(zhMessages.common.select_language),
    )
  })
})
