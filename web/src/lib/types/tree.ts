// Tree types — aligned with backend TreeNode / SpouseNode / TreeResponse

import type { MemberSummary } from './member'

export interface SpouseNode {
  id: string
  full_name: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  death_date?: string
  avatar_url?: string
  relation_subtype: 'married' | 'divorced' | 'widowed' | 'partner'
  start_date?: string
  end_date?: string       // null = still married
  is_primary: boolean
}

export interface TreeNode {
  id: string
  full_name: string
  birth_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_approx: boolean
  death_date?: string
  death_date_approx: boolean
  birth_place?: string
  generation?: number
  avatar_url?: string
  is_clan_member: boolean
  is_clan_founder: boolean
  depth: number
  spouses: SpouseNode[]
  children: TreeNode[]    // recursive
}

export interface PathStep {
  member_id: string
  full_name: string
  avatar_url?: string
  edge_type: 'parent' | 'child' | 'spouse'
  edge_subtype: string
}

export interface RelationshipPath {
  from_member: MemberSummary
  to_member: MemberSummary
  path: PathStep[]
  relationship_description: string  // e.g. "Cháu gọi bằng ông nội"
  degree: number
}
