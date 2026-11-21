import { describe, expect, it, vi } from 'vitest'
import type { FetchLike } from '@/shared/http/api-client'
import type { RequestContext } from '@/shared/http/request-context'
import {
  BIRTHDAY_ID,
  GIO_ID,
  PERSON_ID,
  lunarDeathAnniversaryDto,
  solarBirthdayDto,
} from '../model/event-fixtures'
import { getUpcomingEvents } from './events-repository'

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('getUpcomingEvents', () => {
  it('reads GET /events/upcoming with days and include=person, and maps both events', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: [solarBirthdayDto(), lunarDeathAnniversaryDto()] }),
    )

    const events = await getUpcomingEvents({ days: 365 }, { context, fetchImpl })

    const url = new URL((fetchImpl.mock.calls[0]?.[0] as Request).url)
    expect(url.pathname).toMatch(/\/events\/upcoming$/)
    expect(url.searchParams.get('days')).toBe('365')
    expect(url.searchParams.get('include')).toBe('person')

    expect(events).toEqual([
      {
        id: BIRTHDAY_ID,
        personId: null,
        personName: null,
        personAvatarUrl: null,
        eventType: 'birthday',
        title: 'Sinh nhật bà Lan',
        eventDate: { date: '1950-11-25', precision: 'exact', display: null, lunar: null },
        nextOccurrence: '2026-11-25',
        daysUntil: 4,
        isLunarCalendar: false,
      },
      {
        id: GIO_ID,
        personId: PERSON_ID,
        personName: 'Nguyễn Hữu Đàm',
        personAvatarUrl: null,
        eventType: 'death_anniversary',
        title: 'Giỗ cụ Nguyễn Hữu Đàm',
        eventDate: { date: '1990-12-06', precision: 'exact', display: null, lunar: null },
        nextOccurrence: '2026-12-29',
        daysUntil: 38,
        isLunarCalendar: true,
      },
    ])
  })

  it('reads the flat person fields when the nested person is absent', async () => {
    const dto = lunarDeathAnniversaryDto()
    delete dto.person
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: [dto] }))

    const [event] = await getUpcomingEvents({ days: 30 }, { context, fetchImpl })

    expect(event).toMatchObject({ personId: PERSON_ID, personName: 'Nguyễn Hữu Đàm' })
  })

  it('maps an absent event_date to null rather than inventing one', async () => {
    const dto = solarBirthdayDto()
    delete dto.event_date
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: [dto] }))

    const [event] = await getUpcomingEvents({ days: 30 }, { context, fetchImpl })

    expect(event?.eventDate).toBeNull()
  })

  it('rejects a row without next_occurrence', async () => {
    const dto = lunarDeathAnniversaryDto() as unknown as Record<string, unknown>
    delete dto.next_occurrence
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: [dto] }))

    await expect(getUpcomingEvents({ days: 30 }, { context, fetchImpl })).rejects.toThrow()
  })
})
