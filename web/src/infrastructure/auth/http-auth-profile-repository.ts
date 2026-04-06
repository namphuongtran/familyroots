import type {
  AuthProfileRepository,
  RegisterInput,
  RegisterResult,
} from '@/application/auth/ports/auth-repository'
import api from '@/lib/api/axios'
import type {
  ApiResponse,
  ClanSwitchResponse,
  UserClansResponse,
  UserProfile,
} from '@/lib/types'

type UpdateMeInput = {
  full_name?: string
  preferred_locale?: 'vi' | 'en' | 'zh' | 'fr'
}

export class HttpAuthProfileRepository implements AuthProfileRepository {
  async getMe(): Promise<UserProfile> {
    const { data } = await api.get<ApiResponse<UserProfile>>('/auth/me')
    return data.data
  }

  async updateMe(input: UpdateMeInput): Promise<void> {
    await api.patch('/auth/me', input)
  }

  async listMyClans(): Promise<UserClansResponse> {
    const { data } = await api.get<UserClansResponse>('/me/clans')
    return data
  }

  async selectClan(clanId: string): Promise<ClanSwitchResponse> {
    const { data } = await api.post<ClanSwitchResponse>(`/me/clans/${clanId}/select`)
    return data
  }

  async register(input: RegisterInput): Promise<RegisterResult> {
    const { data } = await api.post<RegisterResult>('/auth/register', input)
    return data
  }
}

export const authProfileRepository = new HttpAuthProfileRepository()
