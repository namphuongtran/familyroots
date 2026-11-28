import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthActions } from '@/features/auth/hooks/use-auth-actions'
import { useSession } from '@/features/auth/hooks/use-session'
import { renderWithProviders } from '@/shared/testing/render'
import RegisterPage from './page'
import messages from '../../../../../messages/vi.json'

/** #333: sign-up points at the privacy notice, next to the submit button. */
vi.mock('@/features/auth/hooks/use-session', () => ({ useSession: vi.fn() }))
vi.mock('@/features/auth/hooks/use-auth-actions', () => ({ useAuthActions: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

describe('sign-up privacy link', () => {
  beforeEach(() => {
    vi.mocked(useSession).mockReturnValue({
      session: null,
      access: { kind: 'signed-out' },
      isLoading: false,
    } as unknown as ReturnType<typeof useSession>)
    vi.mocked(useAuthActions).mockReturnValue({
      register: vi.fn(),
      signInWithGoogle: vi.fn(),
      completeOnboarding: vi.fn(),
      signInWithEmail: vi.fn(),
      signOut: vi.fn(),
    } as unknown as ReturnType<typeof useAuthActions>)
  })

  it('renders a link to /vi/privacy', () => {
    renderWithProviders(<RegisterPage />, { messages })

    const link = screen.getByRole('link', { name: messages.privacy.link })
    expect(link).toHaveAttribute('href', '/vi/privacy')
  })
})
