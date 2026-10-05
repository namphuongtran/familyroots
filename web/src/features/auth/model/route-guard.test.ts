import { describe, expect, it } from 'vitest'
import { getCapabilities } from '@/domain/capability/capability'
import type { Membership, PlatformRole, Session } from '@/domain/session/session'
import { NO_CAPABILITIES } from './capabilities'
import { clanRouteDecision, platformRouteDecision } from './route-guard'

/**
 * #186, ADR-061 § 3-5: where the server guard sends a request, one row per access state, then the
 * capability a page names, then the platform routes. The access state is the real
 * `accessStateOf`, so a branch deleted there fails its row here too.
 */

const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'
const CLAN_B = 'bbbbbbbb-0000-4000-8000-000000000002'
const CLAN_LEFT = 'cccccccc-0000-4000-8000-000000000003'

function membership(clanId: string, role: string): Membership {
  return { clanId, clanName: `Dòng họ ${clanId[0]}`, clanSlug: clanId, role }
}

function session(
  memberships: Membership[],
  {
    platformRole = 'user',
    pending = false,
  }: { platformRole?: PlatformRole; pending?: boolean } = {},
): Session {
  return {
    profile: {
      userId: '11111111-1111-4111-8111-111111111111',
      email: 'lan@example.com',
      fullName: 'Nguyễn Thị Lan',
      preferredLocale: 'vi',
      platformRole,
      hasPendingMembership: pending,
    },
    memberships,
  }
}

const admin = session([membership(CLAN_A, 'admin')])
const viewer = session([membership(CLAN_A, 'viewer')])
const superAdminNoClan = session([], { platformRole: 'super_admin' })

describe('a clan route, by access state', () => {
  it.each([
    { state: 'signed out', who: null, to: '/vi/login' },
    {
      state: 'pending approval',
      who: session([], { pending: true }),
      to: '/vi/pending-approval',
    },
    { state: 'needs onboarding', who: session([]), to: '/vi/register?mode=oauth' },
    {
      state: 'needs clan selection',
      who: session([membership(CLAN_A, 'admin'), membership(CLAN_B, 'viewer')]),
      to: '/vi/select-clan',
    },
    {
      state: 'platform, a super_admin with no membership',
      who: superAdminNoClan,
      to: '/vi/platform/clans',
    },
  ])('$state → $to', ({ who, to }) => {
    expect(clanRouteDecision({ session: who, cookieClanId: null }, null, 'vi')).toEqual({
      kind: 'redirect',
      to,
    })
  })

  it('admits a ready member, with the active clan and what its role grants', () => {
    expect(clanRouteDecision({ session: admin, cookieClanId: CLAN_A }, null, 'vi')).toEqual({
      kind: 'admit',
      session: admin,
      activeClan: admin.memberships[0],
      capabilities: getCapabilities('admin'),
    })
  })

  it('admits the only membership when no cookie names a clan, as on backoffice/*', () => {
    expect(clanRouteDecision({ session: viewer, cookieClanId: null }, null, 'vi')).toMatchObject({
      kind: 'admit',
      activeClan: { clanId: CLAN_A },
    })
  })

  it('sends a cookie naming a clan the user has left to the picker, which rewrites it', () => {
    // The client sends `X-Current-Clan-Id` from the cookie, and the backend refuses a clan the
    // user is not in. Admitted, every clan-scoped request this page sends would be refused.
    expect(clanRouteDecision({ session: viewer, cookieClanId: CLAN_LEFT }, null, 'vi')).toEqual({
      kind: 'redirect',
      to: '/vi/select-clan',
    })
  })

  it('routes in the request locale', () => {
    expect(clanRouteDecision({ session: null, cookieClanId: null }, null, 'en')).toEqual({
      kind: 'redirect',
      to: '/en/login',
    })
  })
})

describe('a clan route that names a capability', () => {
  it('sends a member without it to the dashboard', () => {
    expect(
      clanRouteDecision({ session: viewer, cookieClanId: CLAN_A }, 'viewPendingUsers', 'vi'),
    ).toEqual({ kind: 'redirect', to: '/vi/dashboard' })
  })

  it('admits a member who holds it', () => {
    expect(
      clanRouteDecision({ session: admin, cookieClanId: CLAN_A }, 'viewPendingUsers', 'vi'),
    ).toMatchObject({ kind: 'admit' })
  })

  it('reads the capability, not a rung: an editor holds deleteEvent and not editClanSettings', () => {
    const editor = session([membership(CLAN_A, 'editor')])
    expect(
      clanRouteDecision({ session: editor, cookieClanId: CLAN_A }, 'deleteEvent', 'vi'),
    ).toMatchObject({ kind: 'admit' })
    expect(
      clanRouteDecision({ session: editor, cookieClanId: CLAN_A }, 'editClanSettings', 'vi'),
    ).toEqual({ kind: 'redirect', to: '/vi/dashboard' })
  })

  it('gives a super_admin no bypass: a viewer in the active clan is a viewer', () => {
    const superAdminViewer = session([membership(CLAN_A, 'viewer')], {
      platformRole: 'super_admin',
    })
    expect(
      clanRouteDecision(
        { session: superAdminViewer, cookieClanId: CLAN_A },
        'viewPendingUsers',
        'vi',
      ),
    ).toEqual({ kind: 'redirect', to: '/vi/dashboard' })
  })

  it('grants nothing for a role that is not one of the three', () => {
    const owner = session([membership(CLAN_A, 'owner')])
    expect(
      clanRouteDecision({ session: owner, cookieClanId: CLAN_A }, 'viewPendingUsers', 'vi'),
    ).toEqual({ kind: 'redirect', to: '/vi/dashboard' })
    expect(clanRouteDecision({ session: owner, cookieClanId: CLAN_A }, null, 'vi')).toMatchObject({
      kind: 'admit',
      capabilities: NO_CAPABILITIES,
    })
  })
})

describe('a platform route', () => {
  it('admits a super_admin with no membership', () => {
    expect(platformRouteDecision({ session: superAdminNoClan, cookieClanId: null }, 'vi')).toEqual({
      kind: 'admit',
      session: superAdminNoClan,
    })
  })

  it('admits a super_admin whatever their clans, since the route is not clan-scoped', () => {
    const superAdminOfTwo = session([membership(CLAN_A, 'viewer'), membership(CLAN_B, 'viewer')], {
      platformRole: 'super_admin',
    })
    expect(
      platformRouteDecision({ session: superAdminOfTwo, cookieClanId: null }, 'vi'),
    ).toMatchObject({ kind: 'admit' })
  })

  it.each([
    { state: 'signed out', who: null, to: '/vi/login' },
    { state: 'a clan admin, who is not a super_admin', who: admin, to: '/vi/dashboard' },
    {
      state: 'pending approval',
      who: session([], { pending: true }),
      to: '/vi/pending-approval',
    },
    { state: 'needs onboarding', who: session([]), to: '/vi/register?mode=oauth' },
  ])('sends $state to $to', ({ who, to }) => {
    expect(platformRouteDecision({ session: who, cookieClanId: CLAN_A }, 'vi')).toEqual({
      kind: 'redirect',
      to,
    })
  })
})
