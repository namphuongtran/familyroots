import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { useEvents } from '@/lib/hooks/useEvents'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { EventListClient } from './EventListClient'
import enMessages from '../../../messages/en.json'

/**
 * #194: the empty events list said `Chưa có sự kiện nào.` to every locale.
 *
 * Negative control, 2026-10-06, with the key in all four locale files and the component still
 * holding the literal: `Unable to find an element with the text: No events yet.`, with the
 * Vietnamese sentence in the printed DOM.
 */

vi.mock('@/lib/hooks/useEvents', () => ({ useEvents: vi.fn() }))

describe('the empty events list', () => {
  it('says so in English under the en locale', () => {
    vi.mocked(useEvents).mockReturnValue({
      data: { pages: [{ data: [] }] },
      isLoading: false,
    } as never)
    renderWithProviders(<EventListClient />, { locale: 'en', messages: enMessages })

    expect(screen.getByText(expected(enMessages.events.no_events))).toBeInTheDocument()
  })
})
