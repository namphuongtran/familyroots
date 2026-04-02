'use client'

import {
  useInfiniteQuery,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { personsApi, type PersonsListParams } from '@/lib/api/members'
import type {
  PersonBatchGetInput,
  PersonCreateInput,
  PersonUpdateInput,
} from '@/lib/types'

export const personKeys = {
  all: ['persons'] as const,
  lists: () => [...personKeys.all, 'list'] as const,
  list: (params: PersonsListParams) => [...personKeys.lists(), params] as const,
  search: (q: string) => [...personKeys.all, 'search', q] as const,
  details: () => [...personKeys.all, 'detail'] as const,
  detail: (id: string) => [...personKeys.details(), id] as const,
  marriages: (id: string) => [...personKeys.detail(id), 'marriages'] as const,
  parentChild: (id: string) => [...personKeys.detail(id), 'parent-child'] as const,
  timeline: (id: string) => [...personKeys.detail(id), 'timeline'] as const,
  documents: (id: string) => [...personKeys.detail(id), 'documents'] as const,
  batch: (input: PersonBatchGetInput) => [...personKeys.all, 'batch', input] as const,
}

/** Infinite scroll cursor-paginated person list */
export function usePersons(params: Omit<PersonsListParams, 'cursor'> = {}) {
  return useInfiniteQuery({
    queryKey: personKeys.list(params),
    queryFn: ({ pageParam }) =>
      personsApi.list({ ...params, cursor: pageParam as string | undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })
}

/** Single person detail */
export function usePerson(id: string | undefined) {
  return useQuery({
    queryKey: personKeys.detail(id!),
    queryFn: () => personsApi.get(id!),
    enabled: !!id,
  })
}

/** Debounced trigram search */
export function usePersonSearch(q: string) {
  return useQuery({
    queryKey: personKeys.search(q),
    queryFn: () => personsApi.search(q),
    enabled: q.length >= 2,
    staleTime: 30_000,
  })
}

/** Person's marriages */
export function usePersonMarriages(id: string | undefined) {
  return useQuery({
    queryKey: personKeys.marriages(id!),
    queryFn: () => personsApi.getMarriages(id!),
    enabled: !!id,
  })
}

/** Person's parent-child relationships */
export function usePersonParentChild(id: string | undefined) {
  return useQuery({
    queryKey: personKeys.parentChild(id!),
    queryFn: () => personsApi.getParentChild(id!),
    enabled: !!id,
  })
}

/** Person's timeline */
export function usePersonTimeline(id: string | undefined) {
  return useQuery({
    queryKey: personKeys.timeline(id!),
    queryFn: () => personsApi.getTimeline(id!),
    enabled: !!id,
  })
}

/** Batch person read with optional profile/include/fields/include_by_id. */
export function usePersonsBatch(input: PersonBatchGetInput, enabled = true) {
  return useQuery({
    queryKey: personKeys.batch(input),
    queryFn: () => personsApi.batchGet(input),
    enabled: enabled && input.ids.length > 0,
  })
}

/** Person CRUD mutations */
export function usePersonMutations() {
  const qc = useQueryClient()

  const create = useMutation({
    mutationFn: (input: PersonCreateInput) => personsApi.create(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: personKeys.lists() }),
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: PersonUpdateInput & { id: string }) =>
      personsApi.update(id, input),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: personKeys.detail(id) })
      qc.invalidateQueries({ queryKey: personKeys.lists() })
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => personsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: personKeys.lists() }),
  })

  return { create, update, remove }
}
