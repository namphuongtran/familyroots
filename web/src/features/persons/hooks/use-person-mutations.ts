'use client'

/**
 * TanStack Query mutations over `../server/persons-repository`'s write
 * functions, each invalidating exactly the `persons` cache entries the
 * mutation can have changed. Cross-feature invalidation (e.g. the legacy
 * `personCreateInvalidationKeys`'s `['tree']` row,
 * `src/lib/hooks/query-invalidation.ts`) is explicitly out of scope for this
 * seed (S-030) — it arrives with the second feature slice that needs to
 * invalidate `persons` from outside this feature, per `web/CLAUDE.md`.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { components } from '@/generated/api-types'
import type { RequestContext } from '@/shared/http/request-context'
import {
  createPerson,
  deletePerson,
  restorePerson,
  updatePerson,
} from '../server/persons-repository'
import { personsKeys } from '../server/query-keys'

type PersonCreateRequest = components['schemas']['PersonCreateRequest']
type PersonUpdateRequest = components['schemas']['PersonUpdateRequest']

export interface PersonMutationOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
}

/**
 * `POST /persons`. A new person can only ever affect a list, never a detail that pre-exists it.
 * `mutate`/`mutateAsync` resolve to `PersonWriteResult` (S-032) — `.person` plus a `.warning`
 * string when the write carried `meta.warning` (spec §7.7a) — not a bare `Person`.
 */
export function useCreatePerson(options: PersonMutationOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: PersonCreateRequest) => createPerson(body, { context, refreshAuth }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personsKeys.lists(context.clanId) })
    },
  })
}

/** `PATCH /persons/{id}`. Invalidates the one detail plus every list — a changed field can affect either. */
export function useUpdatePerson(options: PersonMutationOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PersonUpdateRequest }) =>
      updatePerson(id, body, { context, refreshAuth }),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: personsKeys.detail(context.clanId, variables.id) })
      queryClient.invalidateQueries({ queryKey: personsKeys.lists(context.clanId) })
    },
  })
}

/** `DELETE /persons/{id}` — soft delete. Same invalidation shape as update: the row still exists, just hidden. */
export function useDeletePerson(options: PersonMutationOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => deletePerson(id, { context, refreshAuth }),
    onSuccess: (_result, id) => {
      queryClient.invalidateQueries({ queryKey: personsKeys.detail(context.clanId, id) })
      queryClient.invalidateQueries({ queryKey: personsKeys.lists(context.clanId) })
    },
  })
}

/** `POST /persons/{id}/restore`. */
export function useRestorePerson(options: PersonMutationOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => restorePerson(id, { context, refreshAuth }),
    onSuccess: (_result, id) => {
      queryClient.invalidateQueries({ queryKey: personsKeys.detail(context.clanId, id) })
      queryClient.invalidateQueries({ queryKey: personsKeys.lists(context.clanId) })
    },
  })
}
