'use client'

/**
 * TanStack Query wrappers over `../server/persons-repository`'s read
 * functions. A hook's whole job here is composing the repository with a
 * query key from `../server/query-keys` — the repository already did the
 * fetch → parse → map, so nothing in this file touches a DTO or a wire shape.
 *
 * `context` is a `RequestContext` the caller passes in, same as the
 * repository itself takes — no hook here reaches for `getClientRequestContext`
 * internally. A screen (S-031/S-032) is what owns deciding how it gets one,
 * typically `useCurrentClanId()` (`@/shared/http/context.client`) for the
 * reactive clan id plus the rest of the session; wiring that up is a screen
 * concern, not this one, and keeping it out of this file is what makes the
 * hooks below testable with a plain object.
 */

import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import { getPerson, listPersons, searchPersons } from '../server/persons-repository'
import { personsKeys } from '../server/query-keys'
import type {
  GetPersonQuery,
  ListPersonsQuery,
  SearchPersonsQuery,
} from '../server/persons-repository'

export interface PersonsQueryOptions {
  context: RequestContext
  /** Passed straight through to `apiFetch` via the repository. See its own doc comment. */
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

/**
 * `GET /persons`, paginated. `getNextPageParam` reads the opaque cursor
 * straight off the mapped `Page<Person>` and hands it back as the next
 * `pageParam` — never parsed, never constructed, per the cursor rule.
 */
export function usePersonsList(
  query: Omit<ListPersonsQuery, 'cursor'>,
  options: PersonsQueryOptions,
) {
  const { context, refreshAuth, enabled = true } = options
  return useInfiniteQuery({
    queryKey: personsKeys.list(context.clanId, query),
    queryFn: ({ pageParam, signal }) =>
      listPersons({ ...query, cursor: pageParam }, { context, refreshAuth, signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.cursor : undefined),
    enabled,
  })
}

/** `GET /persons/{id}`. */
export function usePerson(id: string, query: GetPersonQuery, options: PersonsQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: personsKeys.detail(context.clanId, id, query),
    queryFn: ({ signal }) => getPerson(id, query, { context, refreshAuth, signal }),
    enabled: enabled && id.length > 0,
  })
}

/** `GET /persons/search`. Disabled for a blank query — there is nothing to search for yet. */
export function usePersonSearch(query: SearchPersonsQuery, options: PersonsQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: personsKeys.search(context.clanId, query),
    queryFn: ({ signal }) => searchPersons(query, { context, refreshAuth, signal }),
    enabled: enabled && query.q.trim().length > 0,
  })
}
