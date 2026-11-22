'use client'

/**
 * TanStack Query wrappers over `../server/admin-repository`. The caller passes the
 * `RequestContext` in, from `useClientRequestContext()`, as in every other slice's hooks.
 *
 * Every mutation that changes who is pending invalidates the users lists and the stats together,
 * because the backoffice's pending count is `stats.pendingUsers`.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ClanRole } from '@/domain/capability/capability'
import type { ClanProfileUpdate } from '@/domain/clan/clan-profile'
import type { RequestContext } from '@/shared/http/request-context'
import {
  approveClanUser,
  changeClanUserRole,
  getClanProfile,
  getClanStats,
  listClanUsers,
  rejectClanUser,
  updateClanProfile,
} from '../server/admin-repository'
import { adminKeys } from '../server/query-keys'

export interface AdminQueryOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

/** `GET /clans/me`. */
export function useClanProfile(options: AdminQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: adminKeys.profile(context.clanId),
    queryFn: ({ signal }) => getClanProfile({ context, refreshAuth, signal }),
    enabled,
  })
}

/** `GET /clans/me?include=stats`. */
export function useClanStats(options: AdminQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: adminKeys.stats(context.clanId),
    queryFn: ({ signal }) => getClanStats({ context, refreshAuth, signal }),
    enabled,
  })
}

/** `PATCH /clans/me`. The stored row it answers with becomes the cached profile. */
export function useUpdateClanProfile(options: AdminQueryOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (update: ClanProfileUpdate) => updateClanProfile(update, { context, refreshAuth }),
    onSuccess: (profile) => {
      queryClient.setQueryData(adminKeys.profile(context.clanId), profile)
    },
  })
}

/** The approved and pending account lists, one page each. */
export function useClanUsers(options: AdminQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: adminKeys.users(context.clanId),
    queryFn: ({ signal }) => listClanUsers({ context, refreshAuth, signal }),
    enabled,
  })
}

/** Approve, reject, and change role. Each invalidates the users lists and the stats. */
export function useClanUserMutations(options: AdminQueryOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()
  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: adminKeys.users(context.clanId) })
    void queryClient.invalidateQueries({ queryKey: adminKeys.stats(context.clanId) })
  }

  const approve = useMutation({
    mutationFn: (userId: string) => approveClanUser(userId, { context, refreshAuth }),
    onSuccess,
  })
  const reject = useMutation({
    mutationFn: (userId: string) => rejectClanUser(userId, { context, refreshAuth }),
    onSuccess,
  })
  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: ClanRole }) =>
      changeClanUserRole(userId, role, { context, refreshAuth }),
    onSuccess,
  })

  return { approve, reject, changeRole }
}
