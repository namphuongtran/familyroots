import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { useAuthActions } from '../hooks/use-auth-actions'
import { useSession } from '../hooks/use-session'
import { SelectClanScreen } from './SelectClanScreen'
import viMessages from '../../../../messages/vi.json'

/**
 * #197: the picker's heading, its paragraph and its button were English literals, so a
 * Vietnamese, Chinese or French reader chose a clan in English. Rendered under `vi`, where no
 * value is the old literal.
 *
 * Negative control, 2026-10-06, with the keys in all four locale files and the screen still
 * holding the literals: the heading case failed with `Unable to find an accessible element with
 * the role "heading" and name "Chọn dòng họ"`, over a DOM whose heading read `Choose your clan`.
 */

vi.mock('../hooks/use-session', () => ({ useSession: vi.fn() }))
vi.mock('../hooks/use-auth-actions', () => ({ useAuthActions: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

/** Two approved memberships, so the screen waits for a choice instead of selecting one itself. */
function twoClans() {
  const memberships = [
    { clanId: 'clan-a', clanName: 'Dòng họ Nguyễn', clanSlug: 'nguyen', role: 'viewer' },
    { clanId: 'clan-b', clanName: 'Dòng họ Trần', clanSlug: 'tran', role: 'viewer' },
  ]
  vi.mocked(useSession).mockReturnValue({
    session: { profile: {} as never, memberships },
    access: { kind: 'needs-clan-selection' },
    activeClan: null,
    isLoading: false,
  } as unknown as ReturnType<typeof useSession>)
  vi.mocked(useAuthActions).mockReturnValue({ selectClan: vi.fn() } as unknown as ReturnType<
    typeof useAuthActions
  >)
}

describe('SelectClanScreen reads in the locale it is rendered under', () => {
  it('heads the screen with the words the invitation link that opens it uses', () => {
    twoClans()
    renderWithProviders(<SelectClanScreen />, { locale: 'vi', messages: viMessages })

    expect(
      screen.getByRole('heading', { name: expected(viMessages.invitation.continue_button) }),
    ).toBeInTheDocument()
  })

  it('says what the choice controls', () => {
    twoClans()
    renderWithProviders(<SelectClanScreen />, { locale: 'vi', messages: viMessages })

    expect(screen.getByText(expected(viMessages.auth.select_clan_subtitle))).toBeInTheDocument()
  })

  it('names the submit button', () => {
    twoClans()
    renderWithProviders(<SelectClanScreen />, { locale: 'vi', messages: viMessages })

    expect(screen.getByRole('button')).toHaveAccessibleName(
      expected(viMessages.member_form.continue_label),
    )
  })
})
