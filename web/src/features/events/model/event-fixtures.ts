/**
 * Wire fixtures for `GET /events/upcoming`, shared by the repository and screen tests. One lunar
 * death anniversary whose recorded solar date (1990-12-06) is not its solar `next_occurrence`
 * (2026-12-29), and one solar birthday whose `next_occurrence` is its recorded day this year.
 */

import type { UpcomingEventDto } from './event-dto'

export const GIO_ID = '7a1d4c1e-0000-4000-8000-000000000001'
export const BIRTHDAY_ID = '7a1d4c1e-0000-4000-8000-000000000002'
export const PERSON_ID = '7a1d4c1e-0000-4000-8000-0000000000a1'

export function lunarDeathAnniversaryDto(): UpcomingEventDto {
  return {
    id: GIO_ID,
    person_id: PERSON_ID,
    person_name: 'Nguyễn Hữu Đàm',
    person_avatar_url: null,
    person: { id: PERSON_ID, full_name: 'Nguyễn Hữu Đàm', avatar_url: null },
    event_type: 'death_anniversary',
    title: 'Giỗ cụ Nguyễn Hữu Đàm',
    event_date: { date: '1990-12-06', precision: 'exact', display: null, lunar: null },
    next_occurrence: '2026-12-29',
    days_until: 38,
    is_lunar_calendar: true,
  }
}

export function solarBirthdayDto(): UpcomingEventDto {
  return {
    id: BIRTHDAY_ID,
    person_id: null,
    person_name: null,
    person_avatar_url: null,
    person: null,
    event_type: 'birthday',
    title: 'Sinh nhật bà Lan',
    event_date: { date: '1950-11-25', precision: 'exact', display: null, lunar: null },
    next_occurrence: '2026-11-25',
    days_until: 4,
    is_lunar_calendar: false,
  }
}
