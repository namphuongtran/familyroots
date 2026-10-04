'use client'

/**
 * The session as server state: one TanStack Query query over `GET /auth/me` and `GET /me/clans`,
 * and the access state derived from it on every read. ADR-061 § 2.
 *
 * It replaces `lib/hooks/useAuth.ts` and the zustand `store/auth.store.ts`. That pair is what ran
 * away on `/vi/dashboard`: each consumer hydrated on mount and wrote fresh objects into the
 * store, which re-ran every consumer, 9037 `GET /auth/me` in twelve seconds as measured on
 * 2026-10-04 (`web/CLAUDE.md`). Here every consumer reads the one cache entry `authKeys.session()`
 * names, so the request count is fixed by design. Nothing is written to `localStorage`.
 *
 * **Supabase's `onAuthStateChange` resets the query, through one subscription per query client
 * however many consumers mount.** A subscription per consumer would turn one auth event into one
 * refetch per component, the runaway's shape again. The first consumer subscribes and the last
 * one to unmount unsubscribes.
 *
 * - `SIGNED_OUT` sets the session to none at once. No request is needed to learn that.
 * - `SIGNED_IN` and `USER_UPDATED` invalidate it, which refetches in the background and keeps the
 *   current value on screen, where a reset would flash every consumer to its loading state.
 *   `@supabase/auth-js` 2.111 also sends `SIGNED_IN` from `_recoverAndRefresh` when a tab becomes
 *   visible again, though only for a session whose user it had to fetch, so a background refetch
 *   is the cheaper answer either way. `cancelRefetch: false` joins a fetch already in flight, such
 *   as the one sign-in itself starts, rather than cancelling it.
 * - `INITIAL_SESSION` and `TOKEN_REFRESHED` change nothing the session query holds.
 */

import { useEffect } from 'react'
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { accessStateOf, type AccessState } from '@/domain/session/access-state'
import type { Membership, Session } from '@/domain/session/session'
import { useCurrentClanId } from '@/shared/http/context.client'
import { onAuthStateChange } from '../api/supabase-auth'
import { fetchSession } from '../server/auth-repository'
import { authKeys } from '../server/query-keys'
import { authRequestContext } from './auth-request-context'

/**
 * Set here rather than inherited from whichever `QueryClient` the hook sits under, so the
 * request count does not depend on a provider default. A minute, as `Providers` uses, keeps a
 * returning tab's refetch-on-focus without one request per mount.
 */
const SESSION_STALE_TIME_MS = 60_000

/** The key the pre-#183 app's zustand `persist` wrote `user`, role and memberships under. */
const LEGACY_AUTH_STORE_KEY = 'auth-store'

/** No Supabase session is "signed out", and costs no request. */
export async function loadSession(): Promise<Session | null> {
  const context = await authRequestContext()
  if (context.accessToken === null) return null
  return fetchSession({ context })
}

/** Signed out, known without asking anyone. Sign-out and Supabase's `SIGNED_OUT` both say so. */
export function clearSession(queryClient: QueryClient): void {
  queryClient.setQueryData<Session | null>(authKeys.session(), null)
}

export function sessionQueryOptions() {
  return {
    queryKey: authKeys.session(),
    queryFn: loadSession,
    staleTime: SESSION_STALE_TIME_MS,
  }
}

/** A browser can hold the old app's persisted copy of the role. Nothing reads it; remove it. */
function forgetLegacyAuthStore(): void {
  try {
    window.localStorage.removeItem(LEGACY_AUTH_STORE_KEY)
  } catch {
    // Storage can be blocked outright. There is then nothing stored to forget.
  }
}

interface SessionSubscription {
  consumers: number
  unsubscribe: () => void
}

const subscriptions = new WeakMap<QueryClient, SessionSubscription>()

function subscribe(queryClient: QueryClient): SessionSubscription {
  forgetLegacyAuthStore()
  const unsubscribe = onAuthStateChange((event) => {
    if (event === 'SIGNED_OUT') {
      clearSession(queryClient)
    } else if (event === 'SIGNED_IN' || event === 'USER_UPDATED') {
      void queryClient.invalidateQueries({ queryKey: authKeys.session() }, { cancelRefetch: false })
    }
  })
  return { consumers: 0, unsubscribe }
}

function useSessionSubscription(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    let subscription = subscriptions.get(queryClient)
    if (!subscription) {
      subscription = subscribe(queryClient)
      subscriptions.set(queryClient, subscription)
    }
    subscription.consumers += 1
    const held = subscription

    return () => {
      held.consumers -= 1
      if (held.consumers === 0) {
        held.unsubscribe()
        subscriptions.delete(queryClient)
      }
    }
  }, [queryClient])
}

export interface SessionState {
  /** `undefined` until the first read finishes; `null` when signed out. */
  session: Session | null | undefined
  /** `null` until the first read finishes, or when it failed. */
  access: AccessState | null
  /** The membership the user acts in when the access state is ready, and `null` otherwise. */
  activeClan: Membership | null
  isLoading: boolean
  isError: boolean
  /** Reads the session again. Rejects when the read fails, rather than resolving the old value. */
  refetch: () => Promise<Session | null | undefined>
}

export function useSession(): SessionState {
  useSessionSubscription()
  const query = useQuery(sessionQueryOptions())
  // Reactive: a clan switch re-derives the access state without touching the query.
  const cookieClanId = useCurrentClanId()
  const access = query.data === undefined ? null : accessStateOf(query.data, cookieClanId)

  return {
    session: query.data,
    access,
    activeClan: access?.kind === 'ready' ? access.activeClan : null,
    isLoading: query.isPending,
    isError: query.isError,
    refetch: async () => (await query.refetch({ throwOnError: true })).data,
  }
}
