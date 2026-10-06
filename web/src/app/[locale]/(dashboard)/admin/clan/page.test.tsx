import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { useClanSettings, useClanSettingsMutation } from '@/lib/hooks/useAdmin'
import { expected, renderWithProviders } from '@/shared/testing/render'
import AdminClanPage from './page'
import viMessages from '../../../../../../messages/vi.json'

/**
 * #194: the clan settings form showed `Loading...` in English to every locale while its settings
 * loaded. It now reads `common.loading`, the key every other loading line uses.
 *
 * Negative control, 2026-10-06, with the component still holding the literal: the vi case failed
 * with `Unable to find an element with the text: Đang tải...`.
 */

vi.mock('@/lib/hooks/useAdmin', () => ({
  useClanSettings: vi.fn(),
  useClanSettingsMutation: vi.fn(),
}))

describe('the clan settings page while its settings load', () => {
  it('says so in Vietnamese under the vi locale', () => {
    vi.mocked(useClanSettings).mockReturnValue({ data: undefined, isLoading: true } as never)
    vi.mocked(useClanSettingsMutation).mockReturnValue({ isPending: false } as never)
    renderWithProviders(<AdminClanPage />, { locale: 'vi', messages: viMessages })

    expect(screen.getByText(expected(viMessages.common.loading))).toBeInTheDocument()
  })
})
