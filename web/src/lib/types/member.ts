// Member types — aligned with backend MemberResponse / MemberCreateRequest

export interface Member {
  id: string
  clan_id: string
  full_name: string
  birth_name?: string
  courtesy_name?: string       // tên tự / tên hiệu
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string          // ISO date string YYYY-MM-DD
  birth_date_approx: boolean   // true = estimated year only
  death_date?: string
  death_date_approx: boolean
  birth_place?: string
  death_place?: string
  residence_place?: string
  generation?: number          // đời thứ
  is_clan_founder: boolean
  is_clan_member: boolean      // false = spouse from another clan
  biography?: string
  avatar_url?: string
  notes?: string
  is_deleted: boolean
  created_by: string
  updated_by?: string
  created_at: string
  updated_at: string
}

/** Lightweight member summary used in lists and tree nodes */
export interface MemberSummary {
  id: string
  full_name: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_approx: boolean
  death_date?: string
  generation?: number
  avatar_url?: string
  is_clan_member: boolean
}

/** Fields for creating or updating a member — mirrors MemberCreateRequest */
export interface MemberCreateInput {
  full_name: string
  birth_name?: string
  courtesy_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_approx: boolean
  death_date?: string
  death_date_approx: boolean
  birth_place?: string
  death_place?: string
  residence_place?: string
  generation?: number
  is_clan_founder: boolean
  is_clan_member: boolean
  biography?: string
  avatar_url?: string
  notes?: string
}

export type MemberUpdateInput = Partial<MemberCreateInput>

/** Timeline event returned by GET /members/{id}/timeline */
export interface TimelineEvent {
  event_date?: string
  date_approx: boolean
  event_type: string
  title: string
  description?: string
  related_member_id?: string
  related_member_name?: string
}
