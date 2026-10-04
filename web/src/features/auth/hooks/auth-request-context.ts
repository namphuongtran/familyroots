import { getClientRequestContext } from '@/shared/http/context.client'
import type { RequestContext } from '@/shared/http/request-context'

/**
 * The request context for this slice's own calls, built here rather than passed in.
 *
 * `web/CLAUDE.md` asks a slice's hooks to take the `RequestContext` their caller passes. The auth
 * slice is the one place that cannot: the session is where the identity behind every other
 * context comes from, so nothing above it holds a context to pass. ADR-061 § 6 gives the browser
 * one shared request context with a `refreshAuth` (#184), and this reads through it once it lands.
 *
 * No `X-Current-Clan-Id`: no auth route is clan-scoped, and a stale cookie naming a clan the user
 * has left must not decide whether their own profile loads.
 */
export async function authRequestContext(): Promise<RequestContext> {
  return { ...(await getClientRequestContext()), clanId: null }
}
