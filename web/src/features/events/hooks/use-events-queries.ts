'use client'

/**
 * TanStack Query wrappers over `../server/events-repository`. The caller passes the
 * `RequestContext` in, from `useClientRequestContext()`, as in the persons and tree hooks.
 */

import { useQuery } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import { getUpcomingEvents } from '../server/events-repository'
import { eventsKeys } from '../server/query-keys'

export interface EventsQueryOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

/** `GET /events/upcoming?days=N`. */
export function useUpcomingEvents(days: number, options: EventsQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: eventsKeys.upcoming(context.clanId, days),
    queryFn: ({ signal }) => getUpcomingEvents({ days }, { context, refreshAuth, signal }),
    enabled,
    staleTime: 5 * 60_000,
  })
}
