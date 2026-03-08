'use client'

import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { eventsApi } from '@/lib/api/events'
import type { CursorPage } from '@/lib/types/api'
import type { ClanEvent } from '@/lib/types'

export const eventKeys = {
  all: ['events'] as const,
  upcoming: (days: number) => [...eventKeys.all, 'upcoming', days] as const,
  list: () => [...eventKeys.all, 'list'] as const,
  detail: (id: string) => [...eventKeys.all, 'detail', id] as const,
}

export function useUpcomingEvents(days = 30) {
  return useQuery({
    queryKey: eventKeys.upcoming(days),
    queryFn: () => eventsApi.getUpcoming(days),
    staleTime: 5 * 60_000,
  })
}

export function useEvents() {
  return useInfiniteQuery<CursorPage<ClanEvent>, Error, { pages: CursorPage<ClanEvent>[]; pageParams: (string | undefined)[] }, readonly unknown[], string | undefined>({
    queryKey: eventKeys.list(),
    queryFn: ({ pageParam }) => eventsApi.list({ cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.next_cursor ?? undefined : undefined,
    staleTime: 60_000,
  })
}
