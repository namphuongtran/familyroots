'use client'

import {
  useInfiniteQuery,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { membersApi, type MembersListParams } from '@/lib/api/members'
import type { MemberCreateInput, MemberUpdateInput } from '@/lib/types'

export const memberKeys = {
  all: ['members'] as const,
  lists: () => [...memberKeys.all, 'list'] as const,
  list: (params: MembersListParams) => [...memberKeys.lists(), params] as const,
  search: (q: string) => [...memberKeys.all, 'search', q] as const,
  details: () => [...memberKeys.all, 'detail'] as const,
  detail: (id: string) => [...memberKeys.details(), id] as const,
  relationships: (id: string) => [...memberKeys.detail(id), 'relationships'] as const,
  timeline: (id: string) => [...memberKeys.detail(id), 'timeline'] as const,
  documents: (id: string) => [...memberKeys.detail(id), 'documents'] as const,
}

/** Infinite scroll cursor-paginated member list */
export function useMembers(params: Omit<MembersListParams, 'cursor'> = {}) {
  return useInfiniteQuery({
    queryKey: memberKeys.list(params),
    queryFn: ({ pageParam }) =>
      membersApi.list({ ...params, cursor: pageParam as string | undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })
}

/** Single member detail */
export function useMember(id: string | undefined) {
  return useQuery({
    queryKey: memberKeys.detail(id!),
    queryFn: () => membersApi.get(id!),
    enabled: !!id,
  })
}

/** Debounced trigram search */
export function useMemberSearch(q: string) {
  return useQuery({
    queryKey: memberKeys.search(q),
    queryFn: () => membersApi.search(q),
    enabled: q.length >= 2,
    staleTime: 30_000,
  })
}

/** Member's relationships */
export function useMemberRelationships(id: string | undefined) {
  return useQuery({
    queryKey: memberKeys.relationships(id!),
    queryFn: () => membersApi.getRelationships(id!),
    enabled: !!id,
  })
}

/** Member's timeline */
export function useMemberTimeline(id: string | undefined) {
  return useQuery({
    queryKey: memberKeys.timeline(id!),
    queryFn: () => membersApi.getTimeline(id!),
    enabled: !!id,
  })
}

/** Member CRUD mutations */
export function useMemberMutations() {
  const qc = useQueryClient()

  const create = useMutation({
    mutationFn: (input: MemberCreateInput) => membersApi.create(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: memberKeys.lists() }),
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: MemberUpdateInput & { id: string }) =>
      membersApi.update(id, input),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: memberKeys.detail(id) })
      qc.invalidateQueries({ queryKey: memberKeys.lists() })
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => membersApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: memberKeys.lists() }),
  })

  return { create, update, remove }
}
