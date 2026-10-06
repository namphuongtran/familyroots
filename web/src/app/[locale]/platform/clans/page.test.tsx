import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { usePlatformClans } from '@/lib/hooks/useAdmin'
import type { PlatformClanSummary } from '@/lib/types'
import { expected, renderWithProviders } from '@/shared/testing/render'
import PlatformClansPage from './page'
import enMessages from '../../../../../messages/en.json'

/**
 * #194: the platform clan list said `Đang tải…` while loading and `Hoạt động` / `Tạm ngưng` on each
 * clan's status, in Vietnamese for every locale. The status is the only text channel the badge
 * has (ADR-055), so an English super_admin could not read it.
 *
 * Negative control, 2026-10-06, with the component still holding the literals: the loading case
 * failed with `Unable to find an element with the text: Loading...`, and the status case with
 * `… with the text: Active`. With only `Tạm ngưng` put back, the status case failed on its second
 * read: `… with the text: Inactive`.
 *
 * `platform.inactive` is "Không hoạt động" in vi, so the Vietnamese badge no longer reads
 * "Tạm ngưng". The pair `platform.active` / `platform.inactive` was written for this field and had
 * no caller; a `suspended` key beside it would be a second word for one state.
 */

vi.mock('@/lib/hooks/useAdmin', () => ({ usePlatformClans: vi.fn() }))

function clan(id: string, isActive: boolean): PlatformClanSummary {
  return { id, name: `Clan ${id}`, slug: `clan-${id}`, is_active: isActive, created_at: null }
}

describe('the platform clan list, under the en locale', () => {
  it('says it is loading in English', () => {
    vi.mocked(usePlatformClans).mockReturnValue({ data: undefined, isLoading: true } as never)
    renderWithProviders(<PlatformClansPage />, { locale: 'en', messages: enMessages })

    expect(screen.getByText(expected(enMessages.common.loading))).toBeInTheDocument()
  })

  it("reads each clan's status in English", () => {
    vi.mocked(usePlatformClans).mockReturnValue({
      data: [clan('a', true), clan('b', false)],
      isLoading: false,
    } as never)
    renderWithProviders(<PlatformClansPage />, { locale: 'en', messages: enMessages })

    expect(screen.getByText(expected(enMessages.platform.active))).toBeInTheDocument()
    expect(screen.getByText(expected(enMessages.platform.inactive))).toBeInTheDocument()
  })
})
