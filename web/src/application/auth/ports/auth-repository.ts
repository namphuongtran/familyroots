import type {
  ClanSwitchResponse,
  UserClansResponse,
  UserProfile,
} from '@/lib/types'

export interface AuthProfileRepository {
  getMe(): Promise<UserProfile>
  updateMe(input: {
    full_name?: string
    preferred_locale?: 'vi' | 'en' | 'zh' | 'fr'
  }): Promise<void>
  listMyClans(): Promise<UserClansResponse>
  selectClan(clanId: string): Promise<ClanSwitchResponse>
}

export interface SessionUser {
  id: string
  email: string
  metadata?: Record<string, unknown>
}

export interface AuthSessionPort {
  getSessionUser(): Promise<SessionUser | null>
  onAuthStateChange(callback: (user: SessionUser | null) => void): () => void
  signInWithEmail(email: string, password: string): Promise<void>
  signUp(email: string, password: string, fullName: string): Promise<void>
  signInWithOAuth(provider: 'google' | 'apple'): Promise<void>
  signOut(): Promise<void>
}