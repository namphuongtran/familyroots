'use client'

/**
 * TanStack Query mutations over `../server/relationships-repository`'s writes (#328). Each one
 * invalidates every `relationships` entry of the active clan: an edge changes the marriages or
 * parent-child list of both people it joins, and the editor cannot know which of them are
 * cached. A change to the tree is the caller's to invalidate (`onChanged` on the editor sheet),
 * because `tree` imports this slice and the reverse import would be a cycle.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { components } from '@/generated/api-types'
import type { RequestContext } from '@/shared/http/request-context'
import {
  createMarriage,
  createParentChild,
  updateMarriage,
} from '../server/relationships-repository'
import { relationshipsKeys } from '../server/query-keys'

type MarriageCreateRequest = components['schemas']['MarriageCreateRequest']
type MarriageUpdateRequest = components['schemas']['MarriageUpdateRequest']
type ParentChildCreateRequest = components['schemas']['ParentChildCreateRequest']

export interface RelationshipMutationOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
}

function useInvalidateRelationships(context: RequestContext) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: relationshipsKeys.all(context.clanId) })
}

/** `POST /relationships/marriages`. */
export function useCreateMarriage({ context, refreshAuth }: RelationshipMutationOptions) {
  const invalidate = useInvalidateRelationships(context)
  return useMutation({
    mutationFn: (body: MarriageCreateRequest) => createMarriage(body, { context, refreshAuth }),
    onSuccess: invalidate,
  })
}

/** `PATCH /relationships/marriages/{id}`. The body carries `expected_version` (ADR-017). */
export function useUpdateMarriage({ context, refreshAuth }: RelationshipMutationOptions) {
  const invalidate = useInvalidateRelationships(context)
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: MarriageUpdateRequest }) =>
      updateMarriage(id, body, { context, refreshAuth }),
    onSuccess: invalidate,
  })
}

/** `POST /relationships/parent-child`. May resolve with a `warning` (spec §7.7a). */
export function useCreateParentChild({ context, refreshAuth }: RelationshipMutationOptions) {
  const invalidate = useInvalidateRelationships(context)
  return useMutation({
    mutationFn: (body: ParentChildCreateRequest) =>
      createParentChild(body, { context, refreshAuth }),
    onSuccess: invalidate,
  })
}
