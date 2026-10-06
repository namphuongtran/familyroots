import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { useClanUserMutations, useClanUsers } from '@/lib/hooks/useAdmin'
import type { ClanUserMembership } from '@/lib/types'
import { expected, renderWithProviders } from '@/shared/testing/render'
import AdminUsersPage from './page'
import viMessages from '../../../../../../messages/vi.json'

/**
 * #194: each approved member's second line was `Person: <id>` or `No linked person`, English for
 * every locale. Both now come from the `admin` namespace, the first with the id as an argument.
 *
 * Negative control, 2026-10-06, with the keys in all four locale files and the page still holding
 * the literals: the linked case failed with `Unable to find an element with the text: Người liên
 * kết: cccccccc-…`, and the unlinked one with `… with the text: Chưa liên kết với người nào`.
 */

vi.mock('@/lib/hooks/useAdmin', () => ({
  useClanUsers: vi.fn(),
  useClanUserMutations: vi.fn(),
}))

const PERSON_ID = 'cccccccc-0000-4000-8000-000000000003'

function member(userId: string, personId: string | null): ClanUserMembership {
  return {
    id: `m-${userId}`,
    user_id: userId,
    role: 'viewer',
    person_id: personId,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function renderPage() {
  vi.mocked(useClanUsers).mockReturnValue({
    data: { approved: [member('u-linked', PERSON_ID), member('u-unlinked', null)], pending: [] },
    isLoading: false,
  } as never)
  vi.mocked(useClanUserMutations).mockReturnValue({
    approve: { mutate: vi.fn() },
    reject: { mutate: vi.fn() },
    changeRole: { mutate: vi.fn() },
  } as never)
  renderWithProviders(<AdminUsersPage />, { locale: 'vi', messages: viMessages })
}

describe("an approved member's linked person, under the vi locale", () => {
  it('names the linked person in Vietnamese', () => {
    renderPage()

    expect(
      screen.getByText(expected(viMessages.admin.linked_person).replace('{id}', PERSON_ID)),
    ).toBeInTheDocument()
  })

  it('says in Vietnamese that no person is linked', () => {
    renderPage()

    expect(screen.getByText(expected(viMessages.admin.no_linked_person))).toBeInTheDocument()
  })
})
