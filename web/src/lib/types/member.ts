// Person types — aligned with backend PersonResponse / PersonCreateRequest

export interface Person {
  id: string
  full_name: string
  birth_name?: string
  courtesy_name?: string       // tên tự / tên hiệu
  posthumous_name?: string     // tên thụy
  alias_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string          // ISO date string YYYY-MM-DD
  birth_date_lunar?: string    // lunar date string
  birth_date_approx: boolean   // true = estimated year only
  death_date?: string
  death_date_lunar?: string
  death_date_approx: boolean
  birth_place?: string
  death_place?: string
  burial_place?: string
  tomb_location?: string
  residence_place?: string
  religion?: string
  nationality?: string
  occupation?: string
  education_level?: string
  title_rank?: string
  phone?: string
  email?: string
  biography?: string
  avatar_url?: string
  notes?: string
  origin_clan_id?: string
  is_deleted: boolean
  created_by: string
  updated_by?: string
  created_at: string
  updated_at: string
  // Clan-context fields (from ClanMembership join)
  membership_role?: 'blood' | 'spouse' | 'adopted'
  generation?: number          // đời thứ (relative to clan)
  is_founder?: boolean
}

/** Lightweight person summary used in lists and tree nodes */
export interface PersonSummary {
  id: string
  full_name: string
  posthumous_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_approx: boolean
  death_date?: string
  generation?: number
  avatar_url?: string
  membership_role?: 'blood' | 'spouse' | 'adopted'
  is_founder?: boolean
}

/** Fields for creating or updating a person — mirrors PersonCreateRequest */
export interface PersonCreateInput {
  full_name: string
  birth_name?: string
  courtesy_name?: string
  posthumous_name?: string
  alias_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_lunar?: string
  birth_date_approx: boolean
  death_date?: string
  death_date_lunar?: string
  death_date_approx: boolean
  birth_place?: string
  death_place?: string
  burial_place?: string
  tomb_location?: string
  residence_place?: string
  religion?: string
  nationality?: string
  occupation?: string
  education_level?: string
  title_rank?: string
  phone?: string
  email?: string
  biography?: string
  avatar_url?: string
  notes?: string
}

export type PersonUpdateInput = Partial<PersonCreateInput>

/** Timeline event returned by GET /persons/{id}/timeline */
export interface TimelineEvent {
  event_date?: string
  date_approx: boolean
  event_type: string
  title: string
  description?: string
  related_person_id?: string
  related_person_name?: string
}
