/**
 * Zod DTOs for the `marriage` wire shapes, constrained to
 * `src/generated/api-types.ts`, plus the mappers from each DTO into
 * `@/domain/relationship`.
 *
 * Every schema here mirrors one generated `components["schemas"][...]` type
 * field for field, including its exact optionality and nullability — not a
 * looser or defensively-widened version of it. `assert*MatchesGenerated`
 * below is what turns drift into a `pnpm type-check` failure: each function's
 * body is `return dto`, so it only compiles while the DTO's inferred type
 * stays assignable to the generated one.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { Marriage, MarriageStatus } from '@/domain/relationship/relationship'
import { historicalDateDtoSchema, toHistoricalDateOrNull } from './historical-date-dto'

/**
 * `backend/app/schemas/relationship.py` constrains status to this set
 * (`status pattern="^(married|divorced|widowed|separated)$"`). The generated
 * type widens it to `string` because the schema encodes it as a regex. The
 * zod schema here is what narrows it back; an unrecognised value fails
 * loudly at the boundary.
 */
const MARRIAGE_STATUSES: readonly MarriageStatus[] = [
  'married',
  'divorced',
  'widowed',
  'separated',
] as const

const nullableString = z.string().nullable().optional()

/** Mirrors `components["schemas"]["MarriageResponse"]`. */
export const marriageResponseDtoSchema = z.object({
  id: z.string(),
  person1_id: z.string(),
  person2_id: z.string(),
  created_by_clan_id: z.string(),
  marriage_date: historicalDateDtoSchema.optional(),
  divorce_date: historicalDateDtoSchema.optional(),
  marriage_place: nullableString,
  status: z.enum(MARRIAGE_STATUSES as unknown as [MarriageStatus, ...MarriageStatus[]]),
  spouse_order: z.number().int().nullable().optional(),
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

export type MarriageResponseDto = z.infer<typeof marriageResponseDtoSchema>

export function assertMarriageResponseDtoMatchesGenerated(
  dto: MarriageResponseDto,
): components['schemas']['MarriageResponse'] {
  return dto
}

export function toMarriage(dto: MarriageResponseDto): Marriage {
  return {
    id: dto.id,
    person1Id: dto.person1_id,
    person2Id: dto.person2_id,
    createdByClanId: dto.created_by_clan_id,
    status: dto.status,
    marriageDate: toHistoricalDateOrNull(dto.marriage_date),
    divorceDate: toHistoricalDateOrNull(dto.divorce_date),
    marriagePlace: dto.marriage_place ?? null,
    spouseOrder: dto.spouse_order ?? null,
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
