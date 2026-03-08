import type { MarriageStatus, ParentChildType } from '@/lib/types/relationship'

/** Vietnamese display labels for marriage statuses */
export const MARRIAGE_STATUS_LABELS: Record<MarriageStatus, string> = {
  married: 'Đã kết hôn',
  divorced: 'Đã ly hôn',
  widowed: 'Đã góa',
  separated: 'Ly thân',
}

/** Vietnamese display labels for parent-child relationship types */
export const PARENT_CHILD_TYPE_LABELS: Record<ParentChildType, string> = {
  biological: 'Con đẻ',
  adopted: 'Con nuôi',
  step: 'Con riêng',
  foster: 'Con nuôi tạm thời',
}

/** English display labels for marriage statuses */
export const MARRIAGE_STATUS_LABELS_EN: Record<MarriageStatus, string> = {
  married: 'Married',
  divorced: 'Divorced',
  widowed: 'Widowed',
  separated: 'Separated',
}

/** English display labels for parent-child relationship types */
export const PARENT_CHILD_TYPE_LABELS_EN: Record<ParentChildType, string> = {
  biological: 'Biological',
  adopted: 'Adopted',
  step: 'Step',
  foster: 'Foster',
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
 * Returns a Vietnamese label for a marriage status.
 */
export function getMarriageStatusLabel(status: string): string {
  return MARRIAGE_STATUS_LABELS[status as MarriageStatus] ?? status
}

/**
 * Returns a Vietnamese label for a parent-child relationship type.
 */
export function getParentChildTypeLabel(type: string): string {
  return PARENT_CHILD_TYPE_LABELS[type as ParentChildType] ?? type
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


