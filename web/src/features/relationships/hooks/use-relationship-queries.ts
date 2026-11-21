'use client'

/**
 * TanStack Query wrappers over `../server/relationships-repository`'s read
 * functions. Same convention as `features/persons/hooks/`: the caller passes
 * in a `RequestContext` from `useClientRequestContext()` — no hook here
 * reaches for a global.
 */

import { useQuery } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import { listPersonMarriages, listPersonParentChild } from '../server/relationships-repository'
import { relationshipsKeys } from '../server/query-keys'

export interface RelationshipsQueryOptions {
  context: RequestContext
  /** Passed straight through to `apiFetch` via the repository. */
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

/** `GET /persons/{person_id}/marriages`. */
export function usePersonMarriages(personId: string, options: RelationshipsQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: relationshipsKeys.personMarriages(context.clanId, personId),
    queryFn: ({ signal }) => listPersonMarriages(personId, { context, refreshAuth, signal }),
    enabled: enabled && personId.length > 0,
  })
}

/** `GET /persons/{person_id}/parent-child`. */
export function usePersonParentChild(personId: string, options: RelationshipsQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: relationshipsKeys.personParentChild(context.clanId, personId),
    queryFn: ({ signal }) => listPersonParentChild(personId, { context, refreshAuth, signal }),
    enabled: enabled && personId.length > 0,
  })
}
