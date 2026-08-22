/**
 * Zod DTOs for the `persons` wire shapes, constrained to
 * `src/generated/api-types.ts`, plus the mappers from each DTO into
 * `@/domain/person`.
 *
 * Every schema here mirrors one generated `components["schemas"][...]` type
 * field for field, including its exact optionality and nullability — not a
 * looser or defensively-widened version of it. `assert*MatchesGenerated`
 * below is what makes a drift between the two a `pnpm type-check` failure:
 * each function's body is nothing but `return dto`, so it only compiles while
 * the DTO's inferred type stays assignable to the generated one. Widening a
 * schema here (e.g. adding `.nullable()` to a field the contract does not
 * mark nullable) would make that function fail to compile too, which is the
 * point — this file must describe what the contract says, not what feels
 * safer.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { Person, PersonActionResult, PersonSearchHit } from '@/domain/person/person'
import {
  historicalDateDtoSchema,
  toHistoricalDate,
  toHistoricalDateOrNull,
} from './historical-date-dto'

/** `backend/app/schemas/person.py:37` and `:95`: `pattern="^(male|female|unknown)$"`. */
const GENDERS = ['male', 'female', 'unknown'] as const

const nullableString = z.string().nullable().optional()

/** Mirrors `components["schemas"]["PersonResponse"]`. */
export const personResponseDtoSchema = z.object({
  id: z.string(),
  created_by_clan_id: nullableString,
  full_name: z.string(),
  birth_name: nullableString,
  courtesy_name: nullableString,
  posthumous_name: nullableString,
  alias_name: nullableString,
  gender: z.enum(GENDERS),
  // Optional, not nullable — the generated type has no `| null` here. See
  // this file's own header comment: match the contract, do not widen it.
  birth_date: historicalDateDtoSchema.optional(),
  death_date: historicalDateDtoSchema.optional(),
  birth_place: nullableString,
  death_place: nullableString,
  burial_place: nullableString,
  tomb_location: nullableString,
  residence_place: nullableString,
  religion: nullableString,
  nationality: z.string(),
  occupation: nullableString,
  education_level: nullableString,
  title_rank: nullableString,
  phone: nullableString,
  email: nullableString,
  biography: nullableString,
  avatar_url: nullableString,
  notes: nullableString,
  is_deleted: z.boolean(),
  created_by: z.string(),
  updated_by: nullableString,
  created_at: z.string(),
  updated_at: z.string(),
  version: z.number(),
})

export type PersonResponseDto = z.infer<typeof personResponseDtoSchema>

export function assertPersonResponseDtoMatchesGenerated(
  dto: PersonResponseDto,
): components['schemas']['PersonResponse'] {
  return dto
}

export function toPerson(dto: PersonResponseDto): Person {
  return {
    id: dto.id,
    createdByClanId: dto.created_by_clan_id ?? null,
    fullName: dto.full_name,
    birthName: dto.birth_name ?? null,
    courtesyName: dto.courtesy_name ?? null,
    posthumousName: dto.posthumous_name ?? null,
    aliasName: dto.alias_name ?? null,
    gender: dto.gender,
    birthDate: toHistoricalDateOrNull(dto.birth_date),
    deathDate: toHistoricalDateOrNull(dto.death_date),
    birthPlace: dto.birth_place ?? null,
    deathPlace: dto.death_place ?? null,
    burialPlace: dto.burial_place ?? null,
    tombLocation: dto.tomb_location ?? null,
    residencePlace: dto.residence_place ?? null,
    religion: dto.religion ?? null,
    nationality: dto.nationality,
    occupation: dto.occupation ?? null,
    educationLevel: dto.education_level ?? null,
    titleRank: dto.title_rank ?? null,
    phone: dto.phone ?? null,
    email: dto.email ?? null,
    biography: dto.biography ?? null,
    avatarUrl: dto.avatar_url ?? null,
    notes: dto.notes ?? null,
    isDeleted: dto.is_deleted,
    createdBy: dto.created_by,
    updatedBy: dto.updated_by ?? null,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    version: dto.version,
  }
}

/** Mirrors `components["schemas"]["PersonSearchResult"]`. */
export const personSearchResultDtoSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  gender: z.enum(GENDERS),
  // Required here, unlike PersonResponse.birth_date — the search projection
  // always includes it.
  birth_date: historicalDateDtoSchema,
  avatar_url: nullableString,
  version: z.number(),
  generation: z.number().nullable().optional(),
  membership_role: nullableString,
  is_founder: z.boolean(),
})

export type PersonSearchResultDto = z.infer<typeof personSearchResultDtoSchema>

export function assertPersonSearchResultDtoMatchesGenerated(
  dto: PersonSearchResultDto,
): components['schemas']['PersonSearchResult'] {
  return dto
}

export function toPersonSearchHit(dto: PersonSearchResultDto): PersonSearchHit {
  return {
    id: dto.id,
    fullName: dto.full_name,
    gender: dto.gender,
    birthDate: toHistoricalDate(dto.birth_date),
    avatarUrl: dto.avatar_url ?? null,
    version: dto.version,
    generation: dto.generation ?? null,
    membershipRole: dto.membership_role ?? null,
    isFounder: dto.is_founder,
  }
}

/** Mirrors `components["schemas"]["MessageData"]` (the `DELETE`/`restore` body). */
export const messageDataDtoSchema = z.object({
  message: z.string(),
  id: nullableString,
})

export type MessageDataDto = z.infer<typeof messageDataDtoSchema>

export function assertMessageDataDtoMatchesGenerated(
  dto: MessageDataDto,
): components['schemas']['MessageData'] {
  return dto
}

export function toPersonActionResult(dto: MessageDataDto): PersonActionResult {
  return { message: dto.message, id: dto.id ?? null }
}

/** Mirrors `components["schemas"]["BatchError"]` — one row of `POST /persons/batch`'s `meta.errors`. */
export const batchErrorDtoSchema = z.object({
  id: z.string(),
  code: z.string(),
})

export type BatchErrorDto = z.infer<typeof batchErrorDtoSchema>

export function assertBatchErrorDtoMatchesGenerated(
  dto: BatchErrorDto,
): components['schemas']['BatchError'] {
  return dto
}
