/**
 * Zod DTOs for the clans-api wire shapes (docs/contracts/rest-clans-api.md), constrained to
 * `src/generated/api-types.ts`, plus their mappers into `@/domain/clan/clan-profile`.
 *
 * Same rule as `features/persons/model/person-dto.ts`: each schema mirrors its generated type
 * field for field, with its exact optionality and nullability, and the `assert…MatchesGenerated`
 * function beside it compiles only while the inferred type stays assignable to the generated one.
 *
 * **`stats` is the one shape with no generated type to check against.** `GET /clans/me` declares
 * `ok(ClanResponse)` (`backend/app/api/v1/clans.py`), and `?include=stats` adds `stats` to the
 * dumped dict afterwards, so OpenAPI never sees it. The schema below mirrors `ClanStats` in
 * `backend/app/schemas/clan.py` and the contract's own example instead. The generated
 * `ClanStatsResponse` is a different, two-field model: the platform clan detail's.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import { CLAN_ROLES, type ClanRole } from '@/domain/capability/capability'
import type {
  ClanProfile,
  ClanProfileUpdate,
  ClanStats,
  ClanUser,
  PendingClanUser,
} from '@/domain/clan/clan-profile'

/** Mirrors `components["schemas"]["ClanResponse"]`. */
export const clanResponseDtoSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  description: z.string().nullish(),
  origin_place: z.string().nullish(),
  founded_year: z.number().nullish(),
  avatar_url: z.string().nullish(),
  motto: z.string().nullish(),
  ancestral_hall_location: z.string().nullish(),
  clan_rules: z.string().nullish(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

export type ClanResponseDto = z.infer<typeof clanResponseDtoSchema>

export function assertClanResponseDtoMatchesGenerated(
  dto: ClanResponseDto,
): components['schemas']['ClanResponse'] {
  return dto
}

/** Mirrors `ClanStats` in `backend/app/schemas/clan.py`; see the header for why not generated. */
export const clanStatsDtoSchema = z.object({
  total_users: z.number().int(),
  approved_users: z.number().int(),
  pending_users: z.number().int(),
  total_members: z.number().int(),
})

export type ClanStatsDto = z.infer<typeof clanStatsDtoSchema>

/** `GET /clans/me?include=stats`: the row, plus `stats`. */
export const clanWithStatsDtoSchema = clanResponseDtoSchema.extend({ stats: clanStatsDtoSchema })

/** Mirrors `components["schemas"]["ClanUserSummary"]`. No `email`, by design (ADR-039). */
export const clanUserSummaryDtoSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  role: z.string(),
  person_id: z.string().nullish(),
  display_name: z.string().nullish(),
  created_at: z.string(),
})

export type ClanUserSummaryDto = z.infer<typeof clanUserSummaryDtoSchema>

export function assertClanUserSummaryDtoMatchesGenerated(
  dto: ClanUserSummaryDto,
): components['schemas']['ClanUserSummary'] {
  return dto
}

/** Mirrors `components["schemas"]["PendingClanUserSummary"]`. */
export const pendingClanUserSummaryDtoSchema = clanUserSummaryDtoSchema.extend({
  email: z.string().nullish(),
})

export type PendingClanUserSummaryDto = z.infer<typeof pendingClanUserSummaryDtoSchema>

export function assertPendingClanUserSummaryDtoMatchesGenerated(
  dto: PendingClanUserSummaryDto,
): components['schemas']['PendingClanUserSummary'] {
  return dto
}

function asClanRole(role: string): ClanRole | null {
  return CLAN_ROLES.includes(role as ClanRole) ? (role as ClanRole) : null
}

export function toClanProfile(dto: ClanResponseDto): ClanProfile {
  return {
    id: dto.id,
    name: dto.name,
    slug: dto.slug,
    description: dto.description ?? null,
    originPlace: dto.origin_place ?? null,
    foundedYear: dto.founded_year ?? null,
    avatarUrl: dto.avatar_url ?? null,
    motto: dto.motto ?? null,
    ancestralHallLocation: dto.ancestral_hall_location ?? null,
    clanRules: dto.clan_rules ?? null,
    isActive: dto.is_active,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export function toClanStats(dto: ClanStatsDto): ClanStats {
  return {
    totalUsers: dto.total_users,
    approvedUsers: dto.approved_users,
    pendingUsers: dto.pending_users,
    totalMembers: dto.total_members,
  }
}

export function toClanUser(dto: ClanUserSummaryDto): ClanUser {
  return {
    id: dto.id,
    userId: dto.user_id,
    role: asClanRole(dto.role),
    personId: dto.person_id ?? null,
    displayName: dto.display_name ?? null,
    createdAt: dto.created_at,
  }
}

export function toPendingClanUser(dto: PendingClanUserSummaryDto): PendingClanUser {
  return { ...toClanUser(dto), email: dto.email ?? null }
}

/** Domain `camelCase` into the `PATCH /clans/me` body. A key left `undefined` is not sent. */
export function toClanUpdateRequest(
  update: ClanProfileUpdate,
): components['schemas']['ClanUpdateRequest'] {
  const body: components['schemas']['ClanUpdateRequest'] = {
    name: update.name,
    description: update.description,
    origin_place: update.originPlace,
    founded_year: update.foundedYear,
    avatar_url: update.avatarUrl,
    motto: update.motto,
    ancestral_hall_location: update.ancestralHallLocation,
    clan_rules: update.clanRules,
  }
  return Object.fromEntries(
    Object.entries(body).filter(([, value]) => value !== undefined),
  ) as components['schemas']['ClanUpdateRequest']
}
