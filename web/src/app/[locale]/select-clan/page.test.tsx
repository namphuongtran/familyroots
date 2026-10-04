import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useAuthActions } from '@/features/auth/hooks/use-auth-actions'
import { useSession } from '@/features/auth/hooks/use-session'
import { ApiError } from '@/shared/http/errors'
import SelectClanPage from './page'
import { renderWithProviders } from '@/shared/testing/render'
import messages from '../../../../messages/vi.json'

/**
 * `selectClan` goes through `apiFetch` since #183, so a refusal is the `ApiError`
 * `parseErrorBody` builds from `docs/contracts/error-codes.md`'s envelope. This test rejects the
 * mocked `selectClan` with that error, and the screen routes on its `code`, never on `.message`.
 * Before #183 the legacy axios client left the envelope at `error.response.data.error`, and the
 * screen read it there.
 */
function clanSuspendedRejection(message = 'Dòng họ đang tạm ngưng') {
  return new ApiError({ code: 'clan_suspended', message, status: 403 })
}

vi.mock('@/features/auth/hooks/use-session', () => ({ useSession: vi.fn() }))
vi.mock('@/features/auth/hooks/use-auth-actions', () => ({ useAuthActions: vi.fn() }))
const pushMock = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: pushMock }) }))

/** One approved membership and no cookie: the access state is ready in it. */
function authWith({ selectClan }: { selectClan: ReturnType<typeof vi.fn> }) {
  const membership = {
    clanId: 'clan-a',
    clanName: 'Dòng họ Nguyễn',
    clanSlug: 'nguyen',
    role: 'viewer',
  }
  vi.mocked(useSession).mockReturnValue({
    session: { profile: {} as never, memberships: [membership] },
    access: { kind: 'ready', activeClan: membership },
    activeClan: membership,
    isLoading: false,
  } as unknown as ReturnType<typeof useSession>)
  vi.mocked(useAuthActions).mockReturnValue({ selectClan } as unknown as ReturnType<
    typeof useAuthActions
  >)
}

describe('select-clan page routes a real clan_suspended rejection to the blocked screen', () => {
  it('the manual "Continue" submit routes on the error code, not the message', async () => {
    const selectClan = vi.fn().mockRejectedValue(clanSuspendedRejection())
    authWith({ selectClan })
    pushMock.mockClear()

    renderWithProviders(<SelectClanPage />, { messages })

    fireEvent.click(
      screen
        .getByLabelText('Dòng họ Nguyễn', { exact: false })
        .closest('label')!
        .querySelector('input')!,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(selectClan).toHaveBeenCalledWith('clan-a'))
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith(
        expect.stringContaining(
          '/clan-suspended?clanId=clan-a&clanName=D%C3%B2ng+h%E1%BB%8D+Nguy%E1%BB%85n',
        ),
      ),
    )
  })

  it('the single-clan auto-select effect routes the same way, instead of an unhandled rejection', async () => {
    const selectClan = vi.fn().mockRejectedValue(clanSuspendedRejection())
    authWith({ selectClan })
    pushMock.mockClear()

    renderWithProviders(<SelectClanPage />, { messages })

    await waitFor(() => expect(selectClan).toHaveBeenCalledWith('clan-a'))
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith(
        expect.stringContaining('/clan-suspended?clanId=clan-a'),
      ),
    )
  })

  it('a non-clan_suspended rejection still falls back to the inline message, unchanged', async () => {
    const selectClan = vi.fn().mockRejectedValue(new Error('boom'))
    authWith({ selectClan })
    pushMock.mockClear()

    renderWithProviders(<SelectClanPage />, { messages })

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument())
    expect(pushMock).not.toHaveBeenCalledWith(expect.stringContaining('clan-suspended'))
  })
})
