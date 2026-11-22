/**
 * Zod DTOs for the platform-admin read shapes, constrained to `src/generated/api-types.ts` by the
 * `assert…MatchesGenerated` functions, as in `features/persons/model/person-dto.ts`.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { PlatformClanSummary, PlatformMetrics } from '@/domain/platform/platform'

/** Mirrors `components["schemas"]["ClanSummaryResponse"]`. */
export const clanSummaryDtoSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  is_active: z.boolean(),
  created_at: z.string().nullish(),
})

export type ClanSummaryDto = z.infer<typeof clanSummaryDtoSchema>

export function assertClanSummaryDtoMatchesGenerated(
  dto: ClanSummaryDto,
): components['schemas']['ClanSummaryResponse'] {
  return dto
}

/** Mirrors `components["schemas"]["PlatformMetricsResponse"]`. */
export const platformMetricsDtoSchema = z.object({
  total_clans: z.number().int(),
  active_clans: z.number().int(),
  suspended_clans: z.number().int(),
  total_members: z.number().int(),
  total_users: z.number().int(),
})

export type PlatformMetricsDto = z.infer<typeof platformMetricsDtoSchema>

export function assertPlatformMetricsDtoMatchesGenerated(
  dto: PlatformMetricsDto,
): components['schemas']['PlatformMetricsResponse'] {
  return dto
}

export function toPlatformClanSummary(dto: ClanSummaryDto): PlatformClanSummary {
  return {
    id: dto.id,
    name: dto.name,
    slug: dto.slug,
    isActive: dto.is_active,
    createdAt: dto.created_at ?? null,
  }
}

export function toPlatformMetrics(dto: PlatformMetricsDto): PlatformMetrics {
  return {
    totalClans: dto.total_clans,
    activeClans: dto.active_clans,
    suspendedClans: dto.suspended_clans,
    totalMembers: dto.total_members,
    totalUsers: dto.total_users,
  }
}
