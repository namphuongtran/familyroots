// Tree types — aligned with backend TreeNode / SpouseNode / TreeResponse

import type { PersonSummary } from './member'

export interface SpouseNode {
  id: string
  full_name: string
  posthumous_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  death_date?: string
  avatar_url?: string
  status: 'married' | 'divorced' | 'widowed' | 'separated'
  marriage_date?: string
  divorce_date?: string
  spouse_order?: number
  membership_role?: 'blood' | 'spouse' | 'adopted'
}

export interface TreeNode {
  id: string
  full_name: string
  birth_name?: string
  posthumous_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_approx: boolean
  death_date?: string
  death_date_approx: boolean
  birth_place?: string
  generation?: number
  avatar_url?: string
  membership_role?: 'blood' | 'spouse' | 'adopted'
  is_founder?: boolean
  depth: number
  // Pedigree-collapse (H4, ADR-027): true on a stub — a lightweight mirror of a
  // person who renders as a FULL node elsewhere in this same payload (their
  // canonical, đời-authority parent). Stubs always have empty spouses/children.
  // The same person id can therefore appear MORE THAN ONCE in one tree payload;
  // consumers that de-duplicate or key elements by bare node id must account
  // for this (see tree-transform.ts's visited-set handling).
  pedigree_collapse_ref?: boolean
  spouses: SpouseNode[]
  children: TreeNode[] // recursive
}

export interface PathStep {
  person_id: string
  full_name: string
  avatar_url?: string
  edge_type: 'parent' | 'child' | 'spouse'
  edge_subtype: string
}

export interface RelationshipPath {
  from_person: PersonSummary
  to_person: PersonSummary
  path: PathStep[]
  relationship_description: string // e.g. "Cháu gọi bằng ông nội"
  degree: number
}
