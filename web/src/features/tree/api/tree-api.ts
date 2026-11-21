/**
 * Transport for docs/contracts/rest-tree-api.md and tree-focus.md. Calls `apiFetch` and
 * nothing else: no React, no parsing. Every function returns the raw enveloped body; the
 * repository parses and maps it.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'

export type TreeApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

export interface GetTreeQuery {
  rootPersonId?: string | null
  maxGenerations?: number
}

export interface GetFocusQuery {
  /** Generations below the focus person, 1–6. */
  descendants?: number
  /** Ancestor generations for the breadcrumb, 0–50. */
  ancestors?: number
}

/** `GET /tree`. */
export function getTree(query: GetTreeQuery, options: TreeApiCallOptions): Promise<unknown> {
  return apiFetch('/tree', {
    ...options,
    method: 'GET',
    query: { root_person_id: query.rootPersonId, max_generations: query.maxGenerations },
  })
}

/** `GET /tree/focus/{person_id}`. */
export function getFocus(
  personId: string,
  query: GetFocusQuery,
  options: TreeApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/tree/focus/${personId}`, {
    ...options,
    method: 'GET',
    query: { descendants: query.descendants, ancestors: query.ancestors },
  })
}
