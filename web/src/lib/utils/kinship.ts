import type { RelationType, RelationSubtype } from '@/lib/types/relationship'

/** Vietnamese display labels for relation types */
export const RELATION_TYPE_LABELS: Record<RelationType, string> = {
  parent: 'Cha / Mẹ',
  child: 'Con',
  spouse: 'Vợ / Chồng',
}

/** Vietnamese display labels for relation subtypes */
export const RELATION_SUBTYPE_LABELS: Record<RelationSubtype, string> = {
  biological: 'Con đẻ',
  adoptive: 'Con nuôi',
  step: 'Con riêng',
  foster: 'Con nuôi tạm thời',
  married: 'Đã kết hôn',
  divorced: 'Đã ly hôn',
  widowed: 'Đã góa',
  partner: 'Bạn đời',
}

/** English display labels */
export const RELATION_TYPE_LABELS_EN: Record<RelationType, string> = {
  parent: 'Parent',
  child: 'Child',
  spouse: 'Spouse',
}

export const RELATION_SUBTYPE_LABELS_EN: Record<RelationSubtype, string> = {
  biological: 'Biological',
  adoptive: 'Adopted',
  step: 'Step',
  foster: 'Foster',
  married: 'Married',
  divorced: 'Divorced',
  widowed: 'Widowed',
  partner: 'Partner',
}

/**
 * Returns Vietnamese kinship terms based on generation difference.
 * Used as a fallback when the API doesn't return a relationship_description.
 */
export function guessKinshipTerm(
  fromGeneration: number | undefined,
  toGeneration: number | undefined,
): string {
  if (fromGeneration == null || toGeneration == null) return 'Người thân'

  const diff = toGeneration - fromGeneration

  const terms: Record<number, string> = {
    0: 'Anh/Chị/Em cùng đời',
    1: 'Con / Cháu',
    '-1': 'Cha / Mẹ',
    2: 'Cháu nội / Cháu ngoại',
    '-2': 'Ông / Bà',
    3: 'Chắt',
    '-3': 'Cụ',
    4: 'Chút',
    '-4': 'Kị',
    5: 'Chít',
    '-5': 'Sơ',
  }

  return terms[diff] ?? `Quan hệ đời thứ ${Math.abs(diff)}`
}

/**
 * Returns a Vietnamese label for a given relation type + optional subtype.
 */
export function getRelationLabel(
  relationType: string,
  relationSubtype?: string | null,
): string {
  const typeLabel = RELATION_TYPE_LABELS[relationType as keyof typeof RELATION_TYPE_LABELS] ?? relationType
  if (!relationSubtype) return typeLabel
  const subtypeLabel = RELATION_SUBTYPE_LABELS[relationSubtype as keyof typeof RELATION_SUBTYPE_LABELS]
  return subtypeLabel ? `${typeLabel} (${subtypeLabel})` : typeLabel
}

/**
 * Format the relationship description from the API into a display string.
 */
export function formatRelationshipDescription(
  description: string,
  fromName: string,
  toName: string,
): string {
  // The backend returns descriptions like "Cháu gọi bằng ông nội"
  // Full sentence: "{fromName} là {description} của {toName}"
  return `${fromName} là ${description} của ${toName}`
}

/** Subtypes available for parent/child relationships */
export const PARENT_CHILD_SUBTYPES: RelationSubtype[] = [
  'biological',
  'adoptive',
  'step',
  'foster',
]

/** Subtypes available for spouse relationships */
export const SPOUSE_SUBTYPES: RelationSubtype[] = [
  'married',
  'divorced',
  'widowed',
  'partner',
]
