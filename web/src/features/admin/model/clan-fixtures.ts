/**
 * Wire fixtures for the clans-api shapes, typed against the generated OpenAPI types so a contract
 * change breaks them at `pnpm type-check`. `stats` has no generated type (see `clan-dto.ts`), so
 * its fixture is typed against the zod DTO.
 */

import type { components } from '@/generated/api-types'
import type { ClanStatsDto } from './clan-dto'

export const CLAN_ID = 'aaaaaaaa-0000-4000-8000-000000000001'

export function clanResponseDto(
  overrides: Partial<components['schemas']['ClanResponse']> = {},
): components['schemas']['ClanResponse'] {
  return {
    id: CLAN_ID,
    name: 'Nguyễn Phúc',
    slug: 'nguyen-phuc',
    description: 'Dòng họ Nguyễn Phúc ở Huế',
    origin_place: 'Huế',
    founded_year: 1750,
    avatar_url: null,
    motto: null,
    ancestral_hall_location: null,
    clan_rules: null,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  }
}

export function clanStatsDto(overrides: Partial<ClanStatsDto> = {}): ClanStatsDto {
  return { total_users: 12, approved_users: 9, pending_users: 3, total_members: 248, ...overrides }
}

export function clanUserDto(
  overrides: Partial<components['schemas']['ClanUserSummary']> = {},
): components['schemas']['ClanUserSummary'] {
  return {
    id: 'r-1',
    user_id: 'u-1',
    role: 'viewer',
    person_id: null,
    display_name: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function pendingClanUserDto(
  overrides: Partial<components['schemas']['PendingClanUserSummary']> = {},
): components['schemas']['PendingClanUserSummary'] {
  return { ...clanUserDto({ id: 'r-p1', user_id: 'u-p1' }), email: null, ...overrides }
}
