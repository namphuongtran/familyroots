import type { Capability, CapabilitySet } from '@/domain/capability/capability'
import { accessStateOf } from '@/domain/session/access-state'
import type { Membership, Session } from '@/domain/session/session'
import { capabilitiesOf } from './capabilities'
import { landingPath } from './landing'

/**
 * Where the server guard sends a request, as a pure function of what the request carries.
 * ADR-061 § 3-5, built by #186. `server/guard.ts` reads the session and the cookie and acts on the
 * decision; this file decides, so the whole table is tested without a request.
 *
 * Every state that is not "ready" goes where `landingPath` sends it, the same table sign-in and
 * the blocked-state screens use. A clan route then asks for a capability, never for a rung on a
 * role ladder (`domain/capability`). A platform route asks only for `platform_role`.
 */

/** What the guard reads off one request. */
export interface GuardInput {
  readonly session: Session | null
  /** The `current_clan_id` cookie, through `parseClanCookie`: null when absent or not a UUID. */
  readonly cookieClanId: string | null
}

export type ClanRouteDecision =
  | { readonly kind: 'redirect'; readonly to: string }
  | {
      readonly kind: 'admit'
      readonly session: Session
      readonly activeClan: Membership
      readonly capabilities: CapabilitySet
    }

export type PlatformRouteDecision =
  | { readonly kind: 'redirect'; readonly to: string }
  | { readonly kind: 'admit'; readonly session: Session }

/**
 * A clan route admits a member who is ready in an active clan, and holds `capability` there when
 * the route names one. A member without it is sent to the dashboard.
 *
 * **A super_admin has no bypass here** (ADR-061 § 4). The backend's clan checks give the role
 * none, and `docs/architecture/rbac.md` makes it platform-level, so a super_admin's clan role is
 * the only thing read. One with no membership is in the `platform` state and lands on
 * `/platform/clans`.
 *
 * **A cookie naming a clan the user is not in goes to the picker**, even when the access state
 * is ready in the only clan they hold. The state is right, but every request the browser sends
 * carries the cookie as `X-Current-Clan-Id`, and the backend refuses that clan. The picker selects
 * a single membership on its own and rewrites the cookie. A cookie that is absent is left alone:
 * `middleware.ts` already sends a `(dashboard)` route without one to the picker, and the backend
 * resolves a single membership with no header, which is how `backoffice/*` is reached.
 */
export function clanRouteDecision(
  { session, cookieClanId }: GuardInput,
  capability: Capability | null,
  locale: string,
): ClanRouteDecision {
  const access = accessStateOf(session, cookieClanId)
  if (session === null || access.kind !== 'ready') {
    return { kind: 'redirect', to: landingPath(access, locale) }
  }

  const { activeClan } = access
  if (cookieClanId !== null && cookieClanId !== activeClan.clanId) {
    return { kind: 'redirect', to: `/${locale}/select-clan` }
  }

  const capabilities = capabilitiesOf(activeClan.role)
  if (capability !== null && !capabilities[capability]) {
    return { kind: 'redirect', to: `/${locale}/dashboard` }
  }
  return { kind: 'admit', session, activeClan, capabilities }
}

/**
 * A platform route admits a super_admin, read from `platform_role` on `GET /auth/me` (ADR-061
 * § 5), whatever clans they hold: `platform/` is not clan-scoped. Anyone else goes where their
 * access state lands, which is the dashboard for a ready member.
 */
export function platformRouteDecision(input: GuardInput, locale: string): PlatformRouteDecision {
  const { session } = input
  if (session?.profile.platformRole === 'super_admin') return { kind: 'admit', session }
  return { kind: 'redirect', to: landingPath(accessStateOf(session, input.cookieClanId), locale) }
}
