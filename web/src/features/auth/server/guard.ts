import 'server-only'

import { cache } from 'react'
import { redirect } from 'next/navigation'
import type { Capability, CapabilitySet } from '@/domain/capability/capability'
import type { Membership, Session } from '@/domain/session/session'
import { getServerRequestContext } from '@/shared/http/context.server'
import type { RequestContext } from '@/shared/http/request-context'
import { clanRouteDecision, platformRouteDecision, type GuardInput } from '../model/route-guard'
import { fetchSession } from './auth-repository'

/**
 * The server guard. ADR-061 § 3-5, built by #186. It replaces the legacy `requireServerRole`,
 * which climbed a role ladder and probed `GET /platform/metrics` to find a super_admin.
 *
 * Three layers route a signed-in user, and this is the middle one. `middleware.ts` checks only
 * that a session and a clan cookie exist, and calls no backend. This guard makes every other
 * routing decision, from the access state the client computes too (`accessStateOf`), so the two
 * runtimes cannot disagree. Client components only render.
 *
 * `../model/route-guard.ts` holds the decision table. This file reads the request and acts on it.
 */

interface RequestSession extends GuardInput {
  readonly context: RequestContext
}

/**
 * The session behind this request: `GET /auth/me` and `GET /me/clans`, sent once however many
 * layouts and pages ask, because React's `cache` keeps one result per server request. A
 * `(dashboard)` page that reads its own context costs no second pair.
 *
 * No `X-Current-Clan-Id` on either: no auth route is clan-scoped, the rule `authCallOptions()`
 * follows in the browser. A visitor with no Supabase session sends nothing.
 *
 * A failed read throws, for the nearest error boundary. It is not an access state: the legacy
 * guard read a failed `GET /me/clans` as "no memberships" and sent approved admins to
 * `/pending-approval`.
 */
const readRequestSession = cache(async (): Promise<RequestSession> => {
  const context = await getServerRequestContext()
  const session =
    context.accessToken === null
      ? null
      : await fetchSession({ context: { ...context, clanId: null } })
  return { session, cookieClanId: context.clanId, context }
})

export interface ClanRoute {
  readonly session: Session
  readonly activeClan: Membership
  /** What the active clan's role grants. A page reads it to decide what it offers. */
  readonly capabilities: CapabilitySet
  /** For this request's own backend calls: its token, and the active clan. */
  readonly context: RequestContext
}

/**
 * Admits a member ready in an active clan, who holds `capability` there when the route names
 * one, and redirects anyone else. See `clanRouteDecision` for where each state goes.
 */
export async function guardClanRoute(
  locale: string,
  capability: Capability | null = null,
): Promise<ClanRoute> {
  const { session, cookieClanId, context } = await readRequestSession()
  const decision = clanRouteDecision({ session, cookieClanId }, capability, locale)
  if (decision.kind === 'redirect') redirect(decision.to)

  return {
    session: decision.session,
    activeClan: decision.activeClan,
    capabilities: decision.capabilities,
    context: { ...context, clanId: decision.activeClan.clanId },
  }
}

export interface PlatformRoute {
  readonly session: Session
  /** For this request's own backend calls. No clan: `platform/` is not clan-scoped. */
  readonly context: RequestContext
}

/** Admits a super_admin, by `platform_role` on `GET /auth/me`, and redirects anyone else. */
export async function guardPlatformRoute(locale: string): Promise<PlatformRoute> {
  const { session, cookieClanId, context } = await readRequestSession()
  const decision = platformRouteDecision({ session, cookieClanId }, locale)
  if (decision.kind === 'redirect') redirect(decision.to)

  return { session: decision.session, context: { ...context, clanId: null } }
}
