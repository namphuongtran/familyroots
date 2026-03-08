import api from './axios'
import type { ApiResponse, UserProfile } from '@/lib/types'

export interface RegisterInput {
  email: string
  password: string
  full_name: string
  clan_action: 'join' | 'create'
  clan_id?: string
  clan_name?: string
  clan_slug?: string
}

export interface RegisterResponse {
  user_id: string
  email: string
  full_name: string
  clan_id: string
  is_approved: boolean
  message: string
}

export const authApi = {
  register: (data: RegisterInput) =>
    api.post<RegisterResponse>('/auth/register', data),

  login: (email: string, password: string) =>
    api.post<{ access_token: string; refresh_token: string; expires_in: number; user: UserProfile }>(
      '/auth/login',
      { email, password },
    ),

  logout: () => api.post('/auth/logout'),

  getProfile: () => api.get<ApiResponse<UserProfile>>('/auth/profile'),

  updateProfile: (data: { full_name?: string; preferred_locale?: 'vi' | 'en' | 'zh' | 'fr' }) =>
    api.patch<ApiResponse<UserProfile>>('/auth/profile', data),

  registerFcmToken: (token: string, device_platform: 'android' | 'ios' | 'web') =>
    api.post('/auth/fcm-token', { token, device_platform }),
}
