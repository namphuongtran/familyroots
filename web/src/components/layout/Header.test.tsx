import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AbstractIntlMessages } from 'next-intl'
import type { AccessState, Membership } from '@/features/auth'
import { useAuthActions, useSession } from '@/features/auth'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { Header } from './Header'
import viMessages from '../../../messages/vi.json'
import zhMessages from '../../../messages/zh.json'

/**
 * #194: the header's clan picker carried three English literals, `Clan` twice and the
 * `Select clan` placeholder option, so a Vietnamese, Chinese or French reader got English beside
 * a translated user menu. Each case renders under a locale whose value is not the literal and
 * reads what a person gets. The placeholder reuses `invitation.continue_button`, which already
 * says "choose a clan" in all four locales, so its English reads "Choose a clan" now.
 *
 * Negative control, 2026-10-06, with the keys in all four locale files and the component still
 * holding the literals: the bar label case failed with
 * `Unable to find an element with the text: Dòng họ`, and the placeholder case with
 * `Unable to find an accessible element with the role "option" and name "选择家族"`, listing
 * `Name "Select clan"` among the options. With only the menu's label put back, the menu case
 * failed alone: `expected [ <span …(1)></span> ] to have a length of 2 but got 1`.
 */

vi.mock('@/features/auth', () => ({ useSession: vi.fn(), useAuthActions: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/vi/dashboard',
}))

const FULL_NAME = 'Nguyễn Thị Lan'
const MEMBERSHIPS: Membership[] = [
  {
    clanId: 'aaaaaaaa-0000-4000-8000-000000000001',
    clanName: 'Nguyễn Phúc',
    clanSlug: 'nguyen-phuc',
    role: 'admin',
  },
  {
    clanId: 'bbbbbbbb-0000-4000-8000-000000000002',
    clanName: 'Trần Văn',
    clanSlug: 'tran-van',
    role: 'viewer',
  },
]

function renderHeader(locale: string, messages: AbstractIntlMessages, access: AccessState) {
  const activeClan = access.kind === 'ready' ? access.activeClan : null
  vi.mocked(useSession).mockReturnValue({
    session: {
      profile: {
        userId: '11111111-1111-4111-8111-111111111111',
        email: 'lan@example.com',
        fullName: FULL_NAME,
        preferredLocale: locale,
        platformRole: 'user',
        hasPendingMembership: false,
      },
      memberships: MEMBERSHIPS,
    },
    access,
    activeClan,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })
  vi.mocked(useAuthActions).mockReturnValue({
    signOut: vi.fn(),
    selectClan: vi.fn(),
  } as unknown as ReturnType<typeof useAuthActions>)
  renderWithProviders(<Header />, { locale, messages })
}

describe('Header clan picker copy', () => {
  it('labels the clan picker in Vietnamese under the vi locale', () => {
    renderHeader('vi', viMessages, { kind: 'ready', activeClan: MEMBERSHIPS[0] })

    expect(screen.getByText(expected(viMessages.common.clan))).toBeInTheDocument()
  })

  it('labels the user menu clan switcher in Vietnamese too', async () => {
    renderHeader('vi', viMessages, { kind: 'ready', activeClan: MEMBERSHIPS[0] })

    await userEvent.click(screen.getByRole('button', { name: FULL_NAME }))

    // The bar's label and the menu's, one key for both.
    expect(screen.getAllByText(expected(viMessages.common.clan))).toHaveLength(2)
  })

  it('offers the placeholder option in Chinese under the zh locale', () => {
    renderHeader('zh', zhMessages, { kind: 'needs-clan-selection' })

    expect(
      screen.getByRole('option', { name: expected(zhMessages.invitation.continue_button) }),
    ).toBeInTheDocument()
  })
})
