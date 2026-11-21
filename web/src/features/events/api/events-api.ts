/**
 * Transport for docs/contracts/rest-events-api.md. Calls `apiFetch` and nothing else: no React,
 * no parsing. Every function returns the raw enveloped body; the repository parses and maps it.
 *
 * Only `GET /events/upcoming` has a caller today, the events page. The list, detail and write
 * routes get a transport with their first screen.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'

export type EventsApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

export interface GetUpcomingEventsQuery {
  /** The window, 1–365 days from the platform's today. */
  days: number
}

/** `GET /events/upcoming?days=N&include=person`. A plain list, not paginated. */
export function getUpcomingEvents(
  query: GetUpcomingEventsQuery,
  options: EventsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/events/upcoming', {
    ...options,
    method: 'GET',
    query: { days: query.days, include: 'person' },
  })
}
