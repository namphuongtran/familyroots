import type {
  ClanAdminCommandRepository,
  ClanAdminQueryRepository,
  PlatformAdminQueryRepository,
} from '@/application/admin/ports/admin-repositories'
import type {
  ClanRole,
  ClanSettings,
  ClanUserMembership,
  PlatformClanSummary,
} from '@/lib/types'

export async function listClanUsers(
  repository: ClanAdminQueryRepository,
): Promise<{
  approved: ClanUserMembership[]
  pending: ClanUserMembership[]
}> {
  const [approved, pending] = await Promise.all([
    repository.listApprovedUsers(),
    repository.listPendingUsers(),
  ])

  return { approved, pending }
}

export function approveClanUser(repository: ClanAdminCommandRepository, userId: string) {
  return repository.approveUser(userId)
}

export function rejectClanUser(repository: ClanAdminCommandRepository, userId: string) {
  return repository.rejectUser(userId)
}

export function removeClanUser(repository: ClanAdminCommandRepository, userId: string) {
  return repository.removeUser(userId)
}

export function changeClanUserRole(
  repository: ClanAdminCommandRepository,
  userId: string,
  role: ClanRole,
) {
  return repository.changeUserRole(userId, role)
}

export function getClanSettings(
  repository: ClanAdminQueryRepository,
  includeStats = false,
): Promise<ClanSettings> {
  return repository.getClanSettings(includeStats)
}

export function updateClanSettings(
  repository: ClanAdminCommandRepository,
  input: Partial<ClanSettings>,
) {
  return repository.updateClanSettings(input)
}

export function listPlatformClans(
  repository: PlatformAdminQueryRepository,
  params?: { cursor?: string; limit?: number },
): Promise<PlatformClanSummary[]> {
  return repository.listClans(params)
}