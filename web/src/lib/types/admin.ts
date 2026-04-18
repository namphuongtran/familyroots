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
  created_at?: string
  updated_at?: string
  stats?: {
    total_users: number
    approved_users: number
    pending_users: number
    total_members: number
  }
}

export interface PlatformClanSummary {
  id: string
  name: string
  slug: string
  is_active: boolean
  created_at?: string | null
}

export interface PlatformMetrics {
  total_clans: number
  active_clans: number
  suspended_clans: number
  total_members: number
  total_users: number
}
