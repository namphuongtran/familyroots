'use client'

/**
 * TanStack Query wrappers over `../server/tree-repository`. The caller passes the
 * `RequestContext` in, from `useClientRequestContext()`, as in the persons hooks.
 */

import { useQuery } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import { getFocus, getTree, type GetFocusQuery, type GetTreeQuery } from '../server/tree-repository'
import { treeKeys } from '../server/query-keys'

export interface TreeQueryOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

const STALE_TIME = 60_000

/** `GET /tree`. */
export function useFamilyTree(query: GetTreeQuery, options: TreeQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: treeKeys.full(context.clanId, query),
    queryFn: ({ signal }) => getTree(query, { context, refreshAuth, signal }),
    enabled,
    staleTime: STALE_TIME,
  })
}

/** `GET /tree/focus/{person_id}`. */
export function useTreeFocus(personId: string, query: GetFocusQuery, options: TreeQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: treeKeys.focus(context.clanId, personId, query),
    queryFn: ({ signal }) => getFocus(personId, query, { context, refreshAuth, signal }),
    enabled: enabled && personId.length > 0,
    staleTime: STALE_TIME,
  })
}
