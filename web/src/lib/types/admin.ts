export type ClanRole = 'admin' | 'editor' | 'viewer'

export interface ClanUserMembership {
  id: string
  user_id: string
  role: ClanRole
  person_id?: string | null
  created_at: string
}

export interface ClanSettings {
  id: string
  name: string
  slug: string
  description?: string | null
  origin_place?: string | null
  founded_year?: number | null
  avatar_url?: string | null
  motto?: string | null
  ancestral_hall_location?: string | null
  clan_rules?: string | null
  is_active: boolean
}

export interface PlatformClanSummary {
  id: string
  name: string
  slug: string
  is_active: boolean
  created_at?: string | null
}