import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EventCalendar } from './EventCalendar'
import { useEvents } from '@/lib/hooks/useEvents'
import { renderWithProviders } from '@/shared/testing/render'
import type { ClanEvent } from '@/lib/types'
import messages from '../../../messages/vi.json'

/**
 * the calendar screen. The month grid used to mark a day that carries an event with a
 * 4px `bg-gold-500` dot and nothing else (`2.03:1` on `background`, measured
 * 2026-08-13, recheck below). That is a single colour channel, so WCAG 1.4.11
 * and spec § 5 `T-06` both fail it, and a screen reader had no way to learn a
 * day carried any events at all (`T-13`).
 *
 * This does not re-measure the token pair's contrast ratio — `bg-primary` /
 * `text-primary-foreground` is already a gated row in `contrast.test.ts`
 * (`{ text: 'primary-foreground', on: 'primary', floor: AA_NORMAL_TEXT }`,
 * plus `everyGround('primary', AA_NORMAL_TEXT)` against every ground the badge
 * can sit on), so adding a second contrast assertion here would just repeat a
 * pair the gate already runs. What this file proves instead is the outcome
 * `.claude/rules/testing.md` "A test pins an outcome, not a setting" asks for:
 * the *accessible name* a screen reader actually computes, not a class string.
 */
vi.mock('@/lib/hooks/useEvents', () => ({ useEvents: vi.fn() }))

const mockUseEvents = vi.mocked(useEvents)

function event(overrides: Partial<ClanEvent>): ClanEvent {
  return {
    id: 'evt-1',
    clan_id: 'clan-1',
    event_type: 'custom',
    title: 'Sự kiện',
    event_date: '2026-08-05',
    is_lunar_calendar: false,
    is_recurring: false,
    notify_days_before: 0,
    created_by: 'user-1',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    ...overrides,
  }
}

function mockEvents(events: ClanEvent[]) {
  mockUseEvents.mockReturnValue({
    data: {
      pages: [{ data: events, has_more: false, next_cursor: null }],
      pageParams: [undefined],
    },
  } as unknown as ReturnType<typeof useEvents>)
}

describe('EventCalendar day marker (spec § 5 T-06/T-13)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-22T00:00:00'))
  })

  afterEach(() => {
    vi.useRealTimers()
    mockUseEvents.mockReset()
  })

  it("announces the event count through the day button's own accessible name, for one event and for several", () => {
    mockEvents([
      event({ id: 'e1', event_date: '2026-08-05' }),
      event({ id: 'e2', event_date: '2026-08-10' }),
      event({ id: 'e3', event_date: '2026-08-10' }),
    ])

    renderWithProviders(<EventCalendar />, { messages })

    // A screen reader computes this from the button's accessible name, not
    // from a sighted read of the badge glyph — this is the assertion that
    // pins the outcome T-13 asks for, not a prop or a class name.
    expect(screen.getByRole('button', { name: /1 sự kiện/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /2 sự kiện/ })).toBeInTheDocument()
  })

  it('leaves a day with no events with its plain digit as the accessible name', () => {
    mockEvents([event({ id: 'e1', event_date: '2026-08-05' })])

    renderWithProviders(<EventCalendar />, { messages })

    // Day 15 has no event. Its accessible name must stay the bare digit --
    // no phantom "sự kiện" announcement.
    expect(screen.getByRole('button', { name: '15' })).toBeInTheDocument()
  })

  it('does not fall back to the sole-colour gold dot for a day that carries an event', () => {
    mockEvents([event({ id: 'e1', event_date: '2026-08-05' })])

    const { container } = renderWithProviders(<EventCalendar />, { messages })

    // Regression guard for the exact defect this seed closes: `bg-gold-500`
    // is legal elsewhere (spec § 2.1's `gilt-decor`, ornament only) but must
    // not be the day marker again, because it is 2.03:1 on `background` and
    // carries no accessible name of its own.
    expect(container.querySelector('.bg-gold-500')).toBeNull()
  })
})
