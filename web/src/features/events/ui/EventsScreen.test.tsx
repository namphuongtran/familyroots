import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AbstractIntlMessages } from 'next-intl'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import viMessages from '../../../../messages/vi.json'
import enMessages from '../../../../messages/en.json'
import type { UpcomingEventDto } from '../model/event-dto'
import { lunarDeathAnniversaryDto, solarBirthdayDto } from '../model/event-fixtures'
import { EventsScreen } from './EventsScreen'

/**
 * #312's reading: an MSW `GET /events/upcoming` holding one lunar death anniversary and one solar
 * birthday. The screen builds its own `RequestContext` through `useClientRequestContext`, so the
 * test drives the real inputs: the clan cookie, and no Supabase session.
 *
 * Only `Date` is faked, to 2026-11-21, so the calendar opens on November 2026; timers stay real
 * so MSW and `findBy*` resolve.
 */
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn(() => null) }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const vi_ = viMessages.events

function serve(events: UpcomingEventDto[]) {
  mswServer.use(http.get(`${API}/events/upcoming`, () => HttpResponse.json(envelope(events))))
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-11-21T09:00:00'))
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
})

afterEach(() => {
  vi.useRealTimers()
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

function card(title: string): HTMLElement {
  return screen.getByRole('heading', { level: 3, name: title }).closest('article')!
}

describe('EventsScreen', () => {
  it('shows both cards; the lunar giỗ is labelled lunar and reads its solar next_occurrence', async () => {
    serve([solarBirthdayDto(), lunarDeathAnniversaryDto()])
    renderWithProviders(<EventsScreen />, {
      messages: viMessages as unknown as AbstractIntlMessages,
    })

    await screen.findByRole('heading', { level: 3, name: 'Giỗ cụ Nguyễn Hữu Đàm' })
    const gio = card('Giỗ cụ Nguyễn Hữu Đàm')
    const birthday = card('Sinh nhật bà Lan')

    // The lunar label, and the backend's converted solar date, not the recorded 06/12.
    expect(within(gio).getByText(expected(vi_.lunar_label))).toBeInTheDocument()
    expect(within(gio).getByText('Giỗ năm nay · 29/12/2026 (dương lịch)')).toBeInTheDocument()
    expect(within(gio).getByText('Ngày ghi trong gia phả: 06/12/1990')).toBeInTheDocument()
    expect(within(gio).getByText('còn 38 ngày')).toBeInTheDocument()
    expect(within(gio).getByText('Nguyễn Hữu Đàm')).toBeInTheDocument()

    // The solar birthday carries no lunar label and reads its next_occurrence plainly.
    expect(within(birthday).queryByText(vi_.lunar_label)).toBeNull()
    expect(within(birthday).getByText('25/11/2026')).toBeInTheDocument()
    expect(within(birthday).getByText('còn 4 ngày')).toBeInTheDocument()
  })

  it('places each event on its next_occurrence in the calendar, and a day filters the list', async () => {
    serve([solarBirthdayDto(), lunarDeathAnniversaryDto()])
    const user = userEvent.setup()
    renderWithProviders(<EventsScreen />, {
      messages: viMessages as unknown as AbstractIntlMessages,
    })
    await screen.findByRole('heading', { level: 3, name: 'Sinh nhật bà Lan' })

    expect(screen.getByRole('button', { name: /25.*1 sự kiện/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: expected(vi_.next_month) }))
    // The giỗ sits on 29 December, its converted date, not on 6 December, its recorded one.
    const dec29 = screen.getByRole('button', { name: /29.*1 sự kiện/ })
    expect(screen.getByRole('button', { name: '6' })).toBeInTheDocument()

    await user.click(dec29)
    expect(screen.getByRole('heading', { level: 3, name: 'Giỗ cụ Nguyễn Hữu Đàm' })).toBeVisible()
    expect(screen.queryByRole('heading', { level: 3, name: 'Sinh nhật bà Lan' })).toBeNull()
  })

  it('says there is nothing upcoming, in English under en', async () => {
    serve([])
    renderWithProviders(<EventsScreen />, {
      locale: 'en',
      messages: enMessages as unknown as AbstractIntlMessages,
    })

    expect(await screen.findByText('No events in the next 365 days.')).toBeInTheDocument()
  })
})
