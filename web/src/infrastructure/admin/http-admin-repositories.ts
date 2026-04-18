import type {
  ClanAdminCommandRepository,
  ClanAdminQueryRepository,
  PlatformAdminQueryRepository,
} from '@/application/admin/ports/admin-repositories'
import api from '@/lib/api/axios'
import type {
  ClanRole,
  ClanSettings,
  ClanUserMembership,
  CursorPage,
  PlatformMetrics,
  PlatformClanSummary,
} from '@/lib/types'

export class HttpClanAdminRepository
  implements ClanAdminQueryRepository, ClanAdminCommandRepository
{
  async listApprovedUsers(params?: {
    cursor?: string
    limit?: number
  }): Promise<ClanUserMembership[]> {
    const { data } = await api.get<{
      data: ClanUserMembership[]
      meta?: { cursor?: string | null; has_more?: boolean }
    }>('/clans/me/users', {
      params,
    })
    return data.data
  }

  async listPendingUsers(params?: {
    cursor?: string
    limit?: number
  }): Promise<ClanUserMembership[]> {
    const { data } = await api.get<CursorPage<ClanUserMembership>>(
      '/clans/me/users/pending',
      { params },
    )
    return data.data
  }

  async getClanSettings(includeStats = false): Promise<ClanSettings> {
    const { data } = await api.get<{ data: ClanSettings }>('/clans/me', {
      params: includeStats ? { include: 'stats' } : undefined,
    })
    return data.data
  }

  async approveUser(userId: string): Promise<void> {
    await api.post(`/clans/me/users/${userId}/approve`)
  }

  async rejectUser(userId: string): Promise<void> {
    await api.post(`/clans/me/users/${userId}/reject`)
  }

  async removeUser(userId: string): Promise<void> {
    await api.delete(`/clans/me/users/${userId}`)
  }

  async changeUserRole(userId: string, role: ClanRole): Promise<void> {
    await api.patch(`/clans/me/users/${userId}/role`, null, {
      params: { role },
    })
  }

  async updateClanSettings(input: Partial<ClanSettings>): Promise<void> {
    await api.patch('/clans/me', input)
  }
}

export class HttpPlatformAdminRepository implements PlatformAdminQueryRepository {
  async listClans(params?: {
    cursor?: string
    limit?: number
  }): Promise<PlatformClanSummary[]> {
    const { data } = await api.get<{
      data: PlatformClanSummary[]
      meta?: { cursor?: string | null; has_more?: boolean }
    }>('/platform/clans', {
      params,
    })
    return data.data
  }

  async getMetrics(): Promise<PlatformMetrics> {
    const { data } = await api.get<{ data: PlatformMetrics }>('/platform/metrics')
    return data.data
  }
}

export const clanAdminRepository = new HttpClanAdminRepository()
export const platformAdminRepository = new HttpPlatformAdminRepository()
