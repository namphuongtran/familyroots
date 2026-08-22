'use client'

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createEvent,
  deleteEvent,
  updateEvent,
} from '@/application/events/use-cases/event-commands'
import { getUpcomingEvents, listEvents } from '@/application/events/use-cases/event-queries'
import { eventCommandRepository } from '@/infrastructure/events/event-command-repository'
import { eventQueryRepository } from '@/infrastructure/events/event-query-repository'
import { eventMutationInvalidationKeys } from '@/lib/hooks/query-invalidation'
import type { CursorPage } from '@/lib/types/api'
import type { ClanEvent, EventCreateInput, EventUpdateInput } from '@/lib/types'

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
  return useInfiniteQuery<
    CursorPage<ClanEvent>,
    Error,
    { pages: CursorPage<ClanEvent>[]; pageParams: (string | undefined)[] },
    readonly unknown[],
    string | undefined
  >({
    queryKey: eventKeys.list(),
    queryFn: ({ pageParam }) => listEvents(eventQueryRepository, { cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? undefined) : undefined,
    staleTime: 60_000,
  })
}

export function useEventMutations() {
  const qc = useQueryClient()

  const invalidateEvents = (options?: { detailId?: string; personId?: string }) => {
    eventMutationInvalidationKeys(options).forEach((queryKey) => {
      qc.invalidateQueries({ queryKey })
    })
  }

  const create = useMutation({
    mutationFn: (input: EventCreateInput) => createEvent(eventCommandRepository, input),
    onSuccess: (event) => invalidateEvents({ personId: event.person_id }),
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: EventUpdateInput & { id: string }) =>
      updateEvent(eventCommandRepository, id, input),
    onSuccess: (event, variables) => {
      invalidateEvents({ detailId: variables.id, personId: event.person_id })
    },
  })

  const remove = useMutation({
    mutationFn: ({ id }: { id: string; personId?: string }) =>
      deleteEvent(eventCommandRepository, id),
    onSuccess: (_data, variables) => {
      invalidateEvents({ detailId: variables.id, personId: variables.personId })
    },
  })

  return { create, update, remove }
}
