/**
 * Zod DTO for `UpcomingEvent`, constrained to `src/generated/api-types.ts` by
 * `assertUpcomingEventDtoMatchesGenerated`, whose body is `return dto`, plus the mapper into
 * `@/domain/event/event`. Same pattern as `features/persons/model/person-dto.ts`.
 *
 * The `HistoricalDate` DTO comes through `@/features/persons`, as the tree slice takes it, rather
 * than a third copy (web/CLAUDE.md, "Tree applied it").
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { UpcomingEvent } from '@/domain/event/event'
import { historicalDateDtoSchema, toHistoricalDate } from '@/features/persons'

type Generated = components['schemas']

const nullableString = z.string().nullable().optional()

/** Mirrors `components["schemas"]["EventPersonSummary"]`. */
export const eventPersonSummaryDtoSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  avatar_url: nullableString,
})

/** Mirrors `components["schemas"]["UpcomingEvent"]`. */
export const upcomingEventDtoSchema = z.object({
  id: z.string(),
  person_id: nullableString,
  person_name: nullableString,
  person_avatar_url: nullableString,
  person: eventPersonSummaryDtoSchema.nullable().optional(),
  event_type: z.string(),
  title: z.string(),
  event_date: historicalDateDtoSchema.optional(),
  next_occurrence: z.string(),
  days_until: z.number().int(),
  is_lunar_calendar: z.boolean(),
})
export type UpcomingEventDto = z.infer<typeof upcomingEventDtoSchema>

export function assertUpcomingEventDtoMatchesGenerated(
  dto: UpcomingEventDto,
): Generated['UpcomingEvent'] {
  return dto
}

export const upcomingEventsDtoSchema = z.array(upcomingEventDtoSchema)

/** `include=person` nests the person; the flat `person_*` fields are the fallback. */
export function toUpcomingEvent(dto: UpcomingEventDto): UpcomingEvent {
  return {
    id: dto.id,
    personId: dto.person?.id ?? dto.person_id ?? null,
    personName: dto.person?.full_name ?? dto.person_name ?? null,
    personAvatarUrl: dto.person?.avatar_url ?? dto.person_avatar_url ?? null,
    eventType: dto.event_type,
    title: dto.title,
    eventDate: dto.event_date === undefined ? null : toHistoricalDate(dto.event_date),
    nextOccurrence: dto.next_occurrence,
    daysUntil: dto.days_until,
    isLunarCalendar: dto.is_lunar_calendar,
  }
}
