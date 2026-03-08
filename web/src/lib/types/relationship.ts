// Relationship types — aligned with backend RelationshipCreateRequest / RelationshipResponse

export type RelationType = 'parent' | 'child' | 'spouse'

export type RelationSubtype =
  | 'biological'  // con đẻ
  | 'adoptive'    // con nuôi
  | 'step'        // con riêng
  | 'foster'      // con nuôi tạm thời
  | 'married'     // đã kết hôn
  | 'divorced'    // đã ly hôn
  | 'widowed'     // đã góa
  | 'partner'     // bạn đời

export interface Relationship {
  id: string
  clan_id: string
  member_id: string
  related_id: string
  relation_type: RelationType
  relation_subtype: RelationSubtype
  start_date?: string
  end_date?: string       // null = active (marriage not ended)
  is_primary: boolean
  notes?: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface RelationshipCreateInput {
  member_id: string
  related_id: string
  relation_type: RelationType
  relation_subtype: RelationSubtype
  start_date?: string
  end_date?: string
  is_primary?: boolean
  notes?: string
}

export type RelationshipUpdateInput = Partial<Omit<RelationshipCreateInput, 'member_id' | 'related_id'>>

export const REL_SUBTYPE_OPTIONS = {
  parent: ['biological', 'adoptive', 'step', 'foster'],
  child: ['biological', 'adoptive', 'step', 'foster'],
  spouse: ['married', 'divorced', 'widowed', 'partner'],
} as const

