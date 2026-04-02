'use client'

import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import {
  getUpcomingEvents,
  listEvents,
} from '@/application/events/use-cases/event-queries'
import { eventQueryRepository } from '@/infrastructure/events/event-query-repository'
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
    queryFn: () => getUpcomingEvents(eventQueryRepository, days),
    staleTime: 5 * 60_000,
  })
}

export function useEvents() {
  return useInfiniteQuery<CursorPage<ClanEvent>, Error, { pages: CursorPage<ClanEvent>[]; pageParams: (string | undefined)[] }, readonly unknown[], string | undefined>({
    queryKey: eventKeys.list(),
    queryFn: ({ pageParam }) => listEvents(eventQueryRepository, { cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.next_cursor ?? undefined : undefined,
    staleTime: 60_000,
  })
}
