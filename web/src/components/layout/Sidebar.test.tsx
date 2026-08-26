import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { renderWithProviders } from '@/shared/testing/render'
import { useUIStore } from '@/store/ui.store'
import { Sidebar } from './Sidebar'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import viMessages from '../../../messages/vi.json'

/**
 * Seed S-092. `Sidebar.tsx:70` carried `aria-label={sidebarOpen ? 'Thu gọn' : 'Mở rộng'}`, a
 * hardcoded Vietnamese pair. It failed in the direction nobody looks for: correct on the default
 * locale a developer is looking at, and Vietnamese in the accessible name for every English,
 * Chinese, and French reader. No visual review catches it, because an `aria-label` is not painted.
 *
 * These cases do two things that "the key exists in en.json" cannot. They render the component
 * under a non-default locale with the real locale file, and they read the label back through the
 * **accessible name** (`toHaveAccessibleName`, computed the way a screen reader computes it)
 * rather than through the `aria-label` attribute.
 *
 * Negative control, run 2026-08-26 with the keys already in all four locale files and the
 * component still holding the literals: the `en` open case failed with
 *
 *     Expected element to have accessible name:
 *       Collapse
 *     Received:
 *       Thu gọn
 *
 * which is the defect stated as a reading rather than as a description.
 */

vi.mock('next/navigation', () => ({ usePathname: () => '/en/dashboard' }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

/** A missing key would make `toHaveAccessibleName(undefined)` assert only "has some name", which
 * the pre-fix Vietnamese literal passes. Fail on the missing key instead of weakening the test. */
function expected(value: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error('the locale file is missing this key')
  }
  return value
}

function renderSidebar(locale: string, messages: AbstractIntlMessages, open: boolean) {
  useUIStore.setState({ sidebarOpen: open })
  renderWithProviders(<Sidebar />, { locale, messages })
  // The rail's only <button> is the collapse/expand toggle; every nav entry is a link.
  return screen.getByRole('button')
}

describe('Sidebar collapse toggle (S-092)', () => {
  it('names the toggle in English under the en locale', () => {
    expect(renderSidebar('en', enMessages, true)).toHaveAccessibleName(
      expected(enMessages.common.collapse),
    )
  })

  it('names the toggle in English under the en locale when collapsed', () => {
    expect(renderSidebar('en', enMessages, false)).toHaveAccessibleName(
      expected(enMessages.common.expand),
    )
  })

  it('names the toggle in Chinese under the zh locale', () => {
    expect(renderSidebar('zh', zhMessages, true)).toHaveAccessibleName(
      expected(zhMessages.common.collapse),
    )
  })

  it('still names the toggle in Vietnamese under the default locale', () => {
    expect(renderSidebar('vi', viMessages, true)).toHaveAccessibleName(
      expected(viMessages.common.collapse),
    )
  })

  it('gives each locale its own word, so no locale reads as a copy of another', () => {
    const collapse = [
      viMessages.common.collapse,
      enMessages.common.collapse,
      zhMessages.common.collapse,
    ]
    expect(new Set(collapse).size).toBe(collapse.length)
  })
})
