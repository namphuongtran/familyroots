import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { useSession, type Membership } from '@/features/auth'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { useUIStore } from '@/store/ui.store'
import { Sidebar } from './Sidebar'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import viMessages from '../../../messages/vi.json'

/**
 * the logout-label fix. `Sidebar.tsx:70` carried `aria-label={sidebarOpen ? 'Thu gọn' : 'Mở rộng'}`, a
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

vi.mock('@/features/auth', () => ({ useSession: vi.fn() }))
vi.mock('next/navigation', () => ({ usePathname: () => '/en/dashboard' }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const ACTIVE_CLAN: Membership = {
  clanId: 'aaaaaaaa-0000-4000-8000-000000000001',
  clanName: 'Nguyễn Phúc',
  clanSlug: 'nguyen-phuc',
  role: 'viewer',
}

/** Signed out, or a member acting in `activeClan`. The toggle cases read neither. */
function sessionWith(activeClan: Membership | null) {
  vi.mocked(useSession).mockReturnValue({
    session: null,
    access: null,
    activeClan,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })
}

beforeEach(() => sessionWith(null))

function renderSidebar(locale: string, messages: AbstractIntlMessages, open: boolean) {
  useUIStore.setState({ sidebarOpen: open })
  renderWithProviders(<Sidebar />, { locale, messages })
  // The rail's only <button> is the collapse/expand toggle; every nav entry is a link.
  return screen.getByRole('button')
}

describe('Sidebar collapse toggle', () => {
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

/**
 * #194: the label above the active clan's name was the literal `Dòng họ`, so every English,
 * Chinese and French reader saw Vietnamese there. It shares one key with the header's two `Clan`
 * labels, because all three say the same word.
 *
 * Negative control, 2026-10-06, with the key in all four locale files and the component still
 * holding the literal: the en case failed with `Unable to find an element with the text: Clan`.
 */
describe('Sidebar active clan label', () => {
  it('labels the active clan in English under the en locale', () => {
    sessionWith(ACTIVE_CLAN)
    renderWithProviders(<Sidebar />, { locale: 'en', messages: enMessages })

    expect(screen.getByText(expected(enMessages.common.clan))).toBeInTheDocument()
  })
})

/**
 * #197: the product name is one literal in every locale, `FamilyRoots`, as on the login and
 * register wordmarks and the backoffice rail. This slot alone said `Gia Phả`, so a Vietnamese
 * reader met two names for one product. The slot is the toggle's row, and the toggle carries no
 * text of its own, so the row's text is the name.
 *
 * Negative control, 2026-10-06, with the slot still holding `Gia Phả`: the vi case failed with
 * `expected 'Gia Phả' to be 'FamilyRoots'`. The en case failed the same way, because the literal
 * read the same under every locale.
 */
describe('Sidebar logo slot', () => {
  it.each([
    ['vi', viMessages],
    ['en', enMessages],
  ] as const)('reads FamilyRoots under the %s locale', (locale, messages) => {
    const toggle = renderSidebar(locale, messages, true)

    expect(toggle.parentElement?.textContent).toBe('FamilyRoots')
  })
})
