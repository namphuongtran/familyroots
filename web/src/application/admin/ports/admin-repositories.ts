import type {
  ClanRole,
  ClanSettings,
  ClanUserMembership,
  PlatformMetrics,
  PlatformClanSummary,
} from '@/lib/types'

export interface ClanAdminQueryRepository {
  listApprovedUsers(params?: { cursor?: string; limit?: number }): Promise<ClanUserMembership[]>
  listPendingUsers(params?: { cursor?: string; limit?: number }): Promise<ClanUserMembership[]>
  getClanSettings(includeStats?: boolean): Promise<ClanSettings>
}

export interface ClanAdminCommandRepository {
  approveUser(userId: string): Promise<void>
  rejectUser(userId: string): Promise<void>
  removeUser(userId: string): Promise<void>
  changeUserRole(userId: string, role: ClanRole): Promise<void>
  updateClanSettings(input: Partial<ClanSettings>): Promise<void>
}

export interface PlatformAdminQueryRepository {
  listClans(params?: { cursor?: string; limit?: number }): Promise<PlatformClanSummary[]>
  getMetrics(): Promise<PlatformMetrics>
}
