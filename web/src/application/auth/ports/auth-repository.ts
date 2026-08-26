import type { ClanSwitchResponse, UserClansResponse, UserProfile } from '@/lib/types'

/**
 * `clan_code` is the join identifier, not `clan_id`. ADR-057 § 2 made the typed identifier
 * the clan **code** (the slug) and `docs/contracts/rest-auth-api.md`'s "The join
 * identifier" table records the release window: the backend accepts either for one
 * release, refuses **both together** with a 422 `auth.clan_code_and_id_both_given`, and
 * then deletes `clan_id`. `clan_id` is dropped from these two shapes rather than kept
 * beside the new field, so nothing in this app can send the pair that is refused, and so
 * the backend's eventual deletion is not a change here. Seed S-082.
 */
export interface RegisterInput {
  email: string
  password: string
  full_name: string
  clan_action: 'join' | 'create'
  clan_code?: string
  clan_name?: string
  clan_slug?: string
}

export interface AuthenticatedOnboardingInput {
  full_name?: string
  clan_action: 'join' | 'create'
  clan_code?: string
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
