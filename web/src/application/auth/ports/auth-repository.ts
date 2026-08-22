import type { ClanSwitchResponse, UserClansResponse, UserProfile } from '@/lib/types'

export interface RegisterInput {
  email: string
  password: string
  full_name: string
  clan_action: 'join' | 'create'
  clan_id?: string
  clan_name?: string
  clan_slug?: string
}

export interface AuthenticatedOnboardingInput {
  full_name?: string
  clan_action: 'join' | 'create'
  clan_id?: string
  clan_name?: string
  clan_slug?: string
}

export interface RegisterResult {
  user_id: string
  email: string
  full_name: string
  clan_id: string
  is_approved: boolean
  message: string
}

export interface AuthProfileRepository {
  getMe(): Promise<UserProfile>
  updateMe(input: {
    full_name?: string
    preferred_locale?: 'vi' | 'en' | 'zh' | 'fr'
  }): Promise<void>
  listMyClans(): Promise<UserClansResponse>
  selectClan(clanId: string): Promise<ClanSwitchResponse>
  register(input: RegisterInput): Promise<RegisterResult>
  onboard(input: AuthenticatedOnboardingInput): Promise<RegisterResult>
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
  signInWithOAuth(provider: 'google' | 'apple'): Promise<void>
  signOut(): Promise<void>
}
