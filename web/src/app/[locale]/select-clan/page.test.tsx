import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useAuth } from '@/lib/hooks/useAuth'
import SelectClanPage from './page'
import { renderWithProviders } from '@/shared/testing/render'
import messages from '../../../../messages/vi.json'

/**
 * `selectClan` (`useAuth.ts`) goes through the legacy axios client
 * (`src/lib/api/axios.ts`), so this test never touches MSW: it rejects the mocked
 * `selectClan` with the same shape `axios.ts`'s interceptor leaves a `403` rejection in —
 * `{ response: { data: { error: { code, message, detail } } } }` (`docs/contracts/error-codes.md`'s
 * envelope, unwrapped one level for the HTTP layer) — the exact shape `backendErrorCode` in
 * `page.tsx` reads. This is the "real, live call site" the S-026 report names: the routing
 * decision under test is on the real `code`, never on `.message`.
 */
function clanSuspendedRejection(message = 'Dòng họ đang tạm ngưng') {
  return {
    response: {
      status: 403,
      data: { error: { code: 'clan_suspended', message, detail: {} } },
    },
  }
}

vi.mock('@/lib/hooks/useAuth', () => ({ useAuth: vi.fn() }))
const pushMock = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: pushMock }) }))

const mockUseAuth = vi.mocked(useAuth)

function authWith(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  return {
    clanMemberships: [
      {
        clan_id: 'clan-a',
        clan_name: 'Dòng họ Nguyễn',
        clan_slug: 'nguyen',
        role: 'viewer' as const,
      },
    ],
    currentClanId: undefined,
    isLoading: false,
    isAuthenticated: true,
    isPendingApproval: false,
    needsOnboarding: false,
    selectClan: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useAuth>
}

describe('select-clan page routes a real clan_suspended rejection to the blocked screen', () => {
  it('the manual "Continue" submit routes on the error code, not the message', async () => {
    const selectClan = vi.fn().mockRejectedValue(clanSuspendedRejection())
    mockUseAuth.mockReturnValue(authWith({ selectClan }))
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
    mockUseAuth.mockReturnValue(authWith({ selectClan, currentClanId: undefined }))
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
    mockUseAuth.mockReturnValue(authWith({ selectClan }))
    pushMock.mockClear()

    renderWithProviders(<SelectClanPage />, { messages })

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument())
    expect(pushMock).not.toHaveBeenCalledWith(expect.stringContaining('clan-suspended'))
  })
})
