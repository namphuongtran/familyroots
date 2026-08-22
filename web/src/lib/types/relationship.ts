// Relationship types — aligned with backend Marriage / ParentChild schemas

export type MarriageStatus = 'married' | 'divorced' | 'widowed' | 'separated'

export type ParentChildType = 'biological' | 'adopted' | 'step' | 'foster'

export interface Marriage {
  id: string
  person1_id: string
  person2_id: string
  created_by_clan_id: string
  status: MarriageStatus
  marriage_date?: string
  divorce_date?: string
  marriage_place?: string
  spouse_order?: number
  notes?: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface MarriageCreateInput {
  person1_id: string
  person2_id: string
  status?: MarriageStatus
  marriage_date?: string
  divorce_date?: string
  marriage_place?: string
  spouse_order?: number
  notes?: string
}

export type MarriageUpdateInput = Partial<Omit<MarriageCreateInput, 'person1_id' | 'person2_id'>>

export interface ParentChild {
  id: string
  parent_id: string
  child_id: string
  created_by_clan_id: string
  relationship_type: ParentChildType
  notes?: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface ParentChildCreateInput {
  parent_id: string
  child_id: string
  relationship_type?: ParentChildType
  notes?: string
}

export type ParentChildUpdateInput = Partial<Omit<ParentChildCreateInput, 'parent_id' | 'child_id'>>

export const PARENT_CHILD_TYPE_OPTIONS: ParentChildType[] = [
  'biological',
  'adopted',
  'step',
  'foster',
]
export const MARRIAGE_STATUS_OPTIONS: MarriageStatus[] = [
  'married',
  'divorced',
  'widowed',
  'separated',
]
