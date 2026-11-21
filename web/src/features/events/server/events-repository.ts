/**
 * The `events` repository: fetch (`../api/events-api`) → parse (`../model/event-dto`) → map to
 * `@/domain/event/event`. Returns domain values only.
 */

import type { UpcomingEvent } from '@/domain/event/event'
import { unwrapData } from '@/shared/http/envelope'
import * as api from '../api/events-api'
import type { EventsApiCallOptions, GetUpcomingEventsQuery } from '../api/events-api'
import { toUpcomingEvent, upcomingEventsDtoSchema } from '../model/event-dto'

export type { EventsApiCallOptions, GetUpcomingEventsQuery }

export async function getUpcomingEvents(
  query: GetUpcomingEventsQuery,
  options: EventsApiCallOptions,
): Promise<UpcomingEvent[]> {
  const body = await api.getUpcomingEvents(query, options)
  return unwrapData(body, (raw) => upcomingEventsDtoSchema.parse(raw).map(toUpcomingEvent))
}
