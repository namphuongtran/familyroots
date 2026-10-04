import { getClientRequestContext, refreshAuthFor } from '@/shared/http/context.client'
import type { AuthApiCallOptions } from '../api/auth-api'

const refreshAuthWithoutClan = refreshAuthFor(null)

/**
 * The request context and `refreshAuth` for this slice's own calls, built here rather than passed
 * in.
 *
 * `web/CLAUDE.md` asks a slice's hooks to take the `RequestContext` their caller passes. The auth
 * slice is the one place that cannot: the session is where the identity behind every other
 * context comes from, so nothing above it holds a context to pass. Its callers are a query
 * function and action callbacks, not components, so it reads `getClientRequestContext()` once per
 * call rather than `useClientRequestContext()`. A read per call is already current, since it asks
 * Supabase for the token every time.
 *
 * `refreshAuth` is the one browser-wide refresh (ADR-061 § 6), so a 401 here shares one
 * `refreshSession()` with every other slice's 401 in the same moment.
 *
 * No `X-Current-Clan-Id`, on the first attempt or the retry: no auth route is clan-scoped, and a
 * stale cookie naming a clan the user has left must not decide whether their own profile loads.
 */
export async function authCallOptions(): Promise<
  Pick<AuthApiCallOptions, 'context' | 'refreshAuth'>
> {
  return {
    context: { ...(await getClientRequestContext()), clanId: null },
    refreshAuth: refreshAuthWithoutClan,
  }
}
