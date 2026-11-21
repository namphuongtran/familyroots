/**
 * Zod DTOs for the parent-child wire shapes, constrained to
 * `src/generated/api-types.ts`, plus the mappers into `@/domain/relationship`.
 *
 * Same discipline as `marriage-dto.ts`: `assertParentChildResponseDtoMatchesGenerated`
 * fails `pnpm type-check` when the backend shape drifts from the one this
 * schema mirrors.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { ParentChild, ParentChildType } from '@/domain/relationship/relationship'

/**
 * `backend/app/schemas/relationship.py` constrains relationship_type to this
 * set. The generated type widens it to `string`; this zod schema narrows it
 * back, and an unrecognised value fails loudly at the boundary.
 */
const PARENT_CHILD_TYPES: readonly ParentChildType[] = [
  'biological',
  'adopted',
  'step',
  'foster',
] as const

const nullableString = z.string().nullable().optional()

/** Mirrors `components["schemas"]["ParentChildResponse"]`. */
export const parentChildResponseDtoSchema = z.object({
  id: z.string(),
  parent_id: z.string(),
  child_id: z.string(),
  created_by_clan_id: z.string(),
  relationship_type: z.enum(
    PARENT_CHILD_TYPES as unknown as [ParentChildType, ...ParentChildType[]],
  ),
  birth_order: z.number().int().nullable().optional(),
  notes: nullableString,
  created_by: z.string(),
  updated_by: nullableString,
  is_deleted: z.boolean(),
  deleted_at: nullableString,
  deleted_by: nullableString,
  created_at: z.string(),
  updated_at: z.string(),
  version: z.number(),
})

export type ParentChildResponseDto = z.infer<typeof parentChildResponseDtoSchema>

export function assertParentChildResponseDtoMatchesGenerated(
  dto: ParentChildResponseDto,
): components['schemas']['ParentChildResponse'] {
  return dto
}

export function toParentChild(dto: ParentChildResponseDto): ParentChild {
  return {
    id: dto.id,
    parentId: dto.parent_id,
    childId: dto.child_id,
    createdByClanId: dto.created_by_clan_id,
    relationshipType: dto.relationship_type,
    birthOrder: dto.birth_order ?? null,
    notes: dto.notes ?? null,
    createdBy: dto.created_by,
    updatedBy: dto.updated_by ?? null,
    isDeleted: dto.is_deleted,
    deletedAt: dto.deleted_at ?? null,
    deletedBy: dto.deleted_by ?? null,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    version: dto.version,
  }
}
