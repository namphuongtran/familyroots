/**
 * The events read model (docs/contracts/rest-events-api.md) in domain shape: camelCase, and every
 * "key absent" normalised to `null`. Types only.
 *
 * Two dates, never conflated (design spec § 7.8, § 9-J7). `eventDate` is the recorded
 * `HistoricalDate`, always a solar date. `nextOccurrence` is the backend-computed solar date of
 * the next anniversary: for a recurring lunar event it is the converted date of the next lunar
 * anniversary (ADR-018), which the client never computes itself.
 */

import type { HistoricalDate } from '@/domain/date/historical-date'

/** One row of `GET /events/upcoming`. */
export interface UpcomingEvent {
  id: string
  personId: string | null
  personName: string | null
  personAvatarUrl: string | null
  /** `death_anniversary`, `birthday`, `wedding_anniversary`, `clan_ceremony` or `custom`. */
  eventType: string
  title: string
  eventDate: HistoricalDate | null
  /** ISO `YYYY-MM-DD`, solar. */
  nextOccurrence: string
  /** Days from the platform's today (`SCHEDULER_TIMEZONE`) to `nextOccurrence`. */
  daysUntil: number
  isLunarCalendar: boolean
}
