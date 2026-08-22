// Person types — aligned with backend PersonResponse
//
// S-033 deleted `PersonCreateInput`, `PersonUpdateInput`, `TimelineEvent`,
// `PersonProfile`, `PersonBatchGetInput`, `PersonBatchGetError`, and
// `PersonBatchGetResponse` from this file: each one's last real reader was
// legacy code this same seed deleted (`src/lib/api/members.ts`'s removed
// methods, `src/infrastructure/http/query-policy.ts`, and
// `src/components/members/*.tsx`).
//
// `Person` stays because `src/lib/hooks/useMembers.ts`'s `usePerson` (kept
// for `MemberSidebar.tsx`, the tree feature) still returns it. `PersonSummary`
// stays because `src/lib/types/tree.ts`'s `RelationshipPath.from_person`/
// `to_person` (kept for the tree feature) still types against it — neither
// of those consumers is a persons-slice file, so neither type could leave
// with the rest. `src/domain/person/person.ts` is the target-contract
// replacement new code should use; this file is what the two legacy
// consumers above still read.

export interface Person {
  id: string
  full_name: string
  birth_name?: string
  courtesy_name?: string // tên tự / tên hiệu
  posthumous_name?: string // tên thụy
  alias_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string // ISO date string YYYY-MM-DD
  birth_date_lunar?: string // lunar date string
  birth_date_approx: boolean // true = estimated year only
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
  generation?: number // đời thứ (relative to clan)
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
