import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/hooks/useAuth'
import { ClanSuspendedScreen } from './ClanSuspendedScreen'
import { renderWithProviders } from '@/shared/testing/render'
import messages from '../../../messages/vi.json'

vi.mock('@/lib/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('next/navigation', () => ({ useSearchParams: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const mockUseAuth = vi.mocked(useAuth)
const mockUseSearchParams = vi.mocked(useSearchParams)

function authWith(clanMemberships: Array<{ clan_id: string; clan_name: string }>) {
  mockUseAuth.mockReturnValue({
    clanMemberships,
    signOut: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>)
}

describe('ClanSuspendedScreen (S-026, spec §7.2c, `403 clan_suspended`)', () => {
  it('offers "switch clan" when the user has another approved clan besides the suspended one', () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('clanId=suspended-1&clanName=D%C3%B2ng%20h%E1%BB%8D%20Nguy%E1%BB%85n') as unknown as ReturnType<
        typeof useSearchParams
      >,
    )
    authWith([
      { clan_id: 'suspended-1', clan_name: 'Dòng họ Nguyễn' },
      { clan_id: 'other-2', clan_name: 'Dòng họ Trần' },
    ])

    renderWithProviders(<ClanSuspendedScreen />, { messages })

    expect(screen.getByText('Dòng họ Dòng họ Nguyễn đang tạm ngưng')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chuyển sang dòng họ khác' })).toBeInTheDocument()
    // T-17: sign-out stays available even though switching is the primary action.
    expect(screen.getByRole('button', { name: 'Đăng xuất' })).toBeInTheDocument()
  })

  it('falls back to sign-out only when the suspended clan is the user\'s only one', () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('clanId=suspended-1&clanName=D%C3%B2ng%20h%E1%BB%8D%20Nguy%E1%BB%85n') as unknown as ReturnType<
        typeof useSearchParams
      >,
    )
    authWith([{ clan_id: 'suspended-1', clan_name: 'Dòng họ Nguyễn' }])

    renderWithProviders(<ClanSuspendedScreen />, { messages })

    expect(screen.queryByRole('link', { name: 'Chuyển sang dòng họ khác' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Đăng xuất' })).toBeInTheDocument()
  })

  it('falls back to the no-name heading when the query param is absent', () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams('clanId=suspended-1') as unknown as ReturnType<typeof useSearchParams>)
    authWith([{ clan_id: 'suspended-1', clan_name: 'Dòng họ Nguyễn' }])

    renderWithProviders(<ClanSuspendedScreen />, { messages })

    expect(screen.getByText('Dòng họ này đang tạm ngưng')).toBeInTheDocument()
  })
})
