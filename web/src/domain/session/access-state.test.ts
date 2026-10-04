import { describe, expect, it } from 'vitest'
import { accessStateOf, activeClanOf } from './access-state'
import type { Membership, PlatformRole, Session } from './session'

/**
 * #183, verification 3: one case per row of the access-state table. Each case reads the
 * function's answer, so deleting one branch of `accessStateOf` turns its row red with the
 * state the remaining branches fall through to.
 */

const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'
const CLAN_B = 'bbbbbbbb-0000-4000-8000-000000000002'
const CLAN_ELSEWHERE = 'cccccccc-0000-4000-8000-000000000003'

function membership(clanId: string, role = 'admin'): Membership {
  return { clanId, clanName: `Dòng họ ${clanId.slice(0, 1)}`, clanSlug: clanId.slice(0, 8), role }
}

function session(
  memberships: Membership[],
  options: { pending?: boolean; platformRole?: PlatformRole } = {},
): Session {
  return {
    profile: {
      userId: '11111111-1111-4111-8111-111111111111',
      email: 'lan@example.com',
      fullName: 'Nguyễn Thị Lan',
      preferredLocale: 'vi',
      platformRole: options.platformRole ?? 'user',
      hasPendingMembership: options.pending ?? false,
    },
    memberships,
  }
}

describe('accessStateOf, the access-state table', () => {
  it('no session → signed out', () => {
    expect(accessStateOf(null, CLAN_A)).toEqual({ kind: 'signed-out' })
  })

  it('no membership and none pending → needs onboarding', () => {
    expect(accessStateOf(session([]), null)).toEqual({ kind: 'needs-onboarding' })
  })

  it('pending only → pending approval', () => {
    expect(accessStateOf(session([], { pending: true }), null)).toEqual({
      kind: 'pending-approval',
    })
  })

  it('approved in A and pending in B → ready in A', () => {
    const a = membership(CLAN_A)

    expect(accessStateOf(session([a], { pending: true }), null)).toEqual({
      kind: 'ready',
      activeClan: a,
    })
  })

  it('two approved and no cookie → needs clan selection', () => {
    expect(accessStateOf(session([membership(CLAN_A), membership(CLAN_B)]), null)).toEqual({
      kind: 'needs-clan-selection',
    })
  })

  it("two approved and a cookie naming a clan the user isn't in → needs clan selection", () => {
    expect(
      accessStateOf(session([membership(CLAN_A), membership(CLAN_B)]), CLAN_ELSEWHERE),
    ).toEqual({ kind: 'needs-clan-selection' })
  })

  it('platform_role super_admin with no membership → platform', () => {
    expect(accessStateOf(session([], { platformRole: 'super_admin' }), null)).toEqual({
      kind: 'platform',
    })
  })

  it('two approved and a cookie naming one of them → ready in that one', () => {
    const b = membership(CLAN_B, 'viewer')

    expect(accessStateOf(session([membership(CLAN_A), b]), CLAN_B)).toEqual({
      kind: 'ready',
      activeClan: b,
    })
  })

  it('a super_admin who also holds a membership acts in it, not on the platform', () => {
    const a = membership(CLAN_A, 'viewer')

    expect(accessStateOf(session([a], { platformRole: 'super_admin' }), null)).toEqual({
      kind: 'ready',
      activeClan: a,
    })
  })
})

/**
 * The one clan resolution both runtimes use. The client's legacy copy also fell back to
 * `profile.clan_id` and the server's did not; this one takes no profile at all.
 */
describe('activeClanOf', () => {
  it('takes the clan the cookie names when the user holds it', () => {
    const b = membership(CLAN_B)
    expect(activeClanOf([membership(CLAN_A), b], CLAN_B)).toBe(b)
  })

  it('takes the only membership when the cookie names none, or names one the user is not in', () => {
    const a = membership(CLAN_A)
    expect(activeClanOf([a], null)).toBe(a)
    expect(activeClanOf([a], CLAN_ELSEWHERE)).toBe(a)
  })

  it('takes nothing when there is no membership, or several and no usable cookie', () => {
    expect(activeClanOf([], CLAN_A)).toBeNull()
    expect(activeClanOf([membership(CLAN_A), membership(CLAN_B)], CLAN_ELSEWHERE)).toBeNull()
  })
})
