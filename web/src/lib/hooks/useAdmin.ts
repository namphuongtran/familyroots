'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  approveClanUser,
  changeClanUserRole,
  getClanSettings,
  getPlatformMetrics,
  listClanUsers,
  listPlatformClans,
  rejectClanUser,
  updateClanSettings,
} from '@/application/admin/use-cases/admin-operations'
import {
  clanAdminRepository,
  platformAdminRepository,
} from '@/infrastructure/admin/http-admin-repositories'
import type {
  ClanRole,
  ClanSettings,
} from '@/lib/types'

export const adminKeys = {
  all: ['admin'] as const,
  users: () => [...adminKeys.all, 'users'] as const,
  clanSettings: () => [...adminKeys.all, 'clan-settings'] as const,
  platformClans: () => [...adminKeys.all, 'platform', 'clans'] as const,
}

export function useClanUsers() {
  return useQuery({
    queryKey: adminKeys.users(),
    queryFn: () => listClanUsers(clanAdminRepository),
  })
}

export function useClanUserMutations() {
  const qc = useQueryClient()

  const approve = useMutation({
    mutationFn: (userId: string) => approveClanUser(clanAdminRepository, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: adminKeys.users() }),
  })

  const reject = useMutation({
    mutationFn: (userId: string) => rejectClanUser(clanAdminRepository, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: adminKeys.users() }),
  })

  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: ClanRole }) =>
      changeClanUserRole(clanAdminRepository, userId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: adminKeys.users() }),
  })

  return { approve, reject, changeRole }
}

export function useClanSettings() {
  return useQuery({
    queryKey: adminKeys.clanSettings(),
    queryFn: () => getClanSettings(clanAdminRepository),
  })
}

export function useClanSettingsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: Partial<ClanSettings>) =>
      updateClanSettings(clanAdminRepository, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: adminKeys.clanSettings() }),
  })
}

export function usePlatformClans() {
  return useQuery({
    queryKey: adminKeys.platformClans(),
    queryFn: () => listPlatformClans(platformAdminRepository),
  })
}

export function usePlatformMetrics() {
  return useQuery({
    queryKey: [...adminKeys.all, 'platform', 'metrics'] as const,
    queryFn: () => getPlatformMetrics(platformAdminRepository),
  })
}
