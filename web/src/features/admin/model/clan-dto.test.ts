import { describe, expect, it } from 'vitest'
import {
  clanWithStatsDtoSchema,
  pendingClanUserSummaryDtoSchema,
  toClanStats,
  toClanUpdateRequest,
  toPendingClanUser,
} from './clan-dto'
import { clanResponseDto, clanStatsDto, pendingClanUserDto } from './clan-fixtures'

describe('the clans-api mappers', () => {
  it('maps each stats count to its own domain field', () => {
    const dto = clanWithStatsDtoSchema.parse({
      ...clanResponseDto(),
      stats: clanStatsDto({
        total_users: 1,
        approved_users: 2,
        pending_users: 3,
        total_members: 4,
      }),
    })
    expect(toClanStats(dto.stats)).toEqual({
      totalUsers: 1,
      approvedUsers: 2,
      pendingUsers: 3,
      totalMembers: 4,
    })
  })

  it('refuses a GET /clans/me body without stats when stats were asked for', () => {
    expect(() => clanWithStatsDtoSchema.parse(clanResponseDto())).toThrow()
  })

  it('narrows a role it cannot name to null, and keeps the pending email', () => {
    const user = toPendingClanUser(
      pendingClanUserDto({ role: 'owner', email: 'hoa@example.com', display_name: undefined }),
    )
    expect(user.role).toBeNull()
    expect(user.email).toBe('hoa@example.com')
    expect(user.displayName).toBeNull()
    expect(
      toPendingClanUser(
        pendingClanUserSummaryDtoSchema.parse(pendingClanUserDto({ role: 'editor' })),
      ).role,
    ).toBe('editor')
  })

  it('sends only the keys an update names', () => {
    expect(toClanUpdateRequest({ name: 'A', originPlace: null })).toEqual({
      name: 'A',
      origin_place: null,
    })
  })
})
