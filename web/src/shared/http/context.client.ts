'use client'

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { createClientOrNull } from '@/shared/supabase/client'
import { createSingleFlight } from './refresh'
import {
  CLAN_COOKIE,
  localeFromPathname,
  parseClanCookie,
  type RequestContext,
} from './request-context'

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/**
 * Notifies `useCurrentClanId` subscribers after `writeClanCookie` /
 * `clearClanCookie` change the cookie. `document.cookie` writes fire no
 * native change event, so this is the only way a switch re-renders anything
 * without a page reload.
 */
const clanCookieListeners = new Set<() => void>()

function notifyClanCookieChanged(): void {
  for (const listener of clanCookieListeners) listener()
}

function subscribeToClanCookieChanges(listener: () => void): () => void {
  clanCookieListeners.add(listener)
  return () => {
    clanCookieListeners.delete(listener)
  }
}

const ONE_YEAR_IN_SECONDS = 60 * 60 * 24 * 365

/**
 * The cookie's attributes, decided here because this is the one place the
 * write and the read (`readCookie` above, `context.server.ts`) have to agree.
 * The capability module through the legacy-component deletion inherit this shape rather than re-deciding it:
 *
 * - `httpOnly` is not set, i.e. false. This is forced, not chosen:
 *   `getClientRequestContext` above reads the cookie through `document.cookie`,
 *   and a script that can read a cookie can by definition set it, so declaring
 *   `httpOnly` here would be theatre. The cookie also is not a credential — it
 *   is a routing hint the backend re-validates against the caller's actual
 *   memberships on every request (`get_current_clan_id`,
 *   `docs/architecture/multi-tenancy.md`) — so nothing sensitive would leak by
 *   it being script-readable.
 * - `sameSite=lax` sends the cookie on a normal top-level navigation (an SSO
 *   redirect, a typed URL) but not on a cross-site subrequest or form post,
 *   which is the standard mitigation for a script-writable cookie. Matches
 *   what the legacy writer used to ship, back when one existed
 *   (`src/infrastructure/auth/clan-selection-storage.ts`, deleted by the legacy-transport deletion once nothing
 *   imported it — the auth-store split had already moved both real callers off it).
 * - `secure` is added only when the page itself is served over `https:`.
 *   `document.cookie` silently drops a `Secure` attribute set from an
 *   insecure origin rather than erroring, so hard-coding it would break local
 *   `http://localhost` dev instead of protecting anything.
 * - `path=/` — every locale-prefixed route needs to read it, and so does
 *   `web/src/middleware.ts`, which runs before any narrower path is known.
 * - `max-age` one year: this is a UI preference the backend re-validates, not
 *   a session credential, so there is no security reason to expire it sooner.
 */
function clanCookieAttributes(): string {
  const secure = typeof location !== 'undefined' && location.protocol === 'https:' ? '; secure' : ''
  return `path=/; max-age=${ONE_YEAR_IN_SECONDS}; samesite=lax${secure}`
}

/**
 * Selecting a clan writes this cookie. `useAuth`'s `selectClan` and
 * `syncAuthContext` call this now instead of the legacy
 * `persistCurrentClanId` (`src/infrastructure/auth/clan-selection-storage.ts`, same
 * cookie name, compatible attributes, but it also wrote `localStorage.current_clan_id` —
 * deliberately not carried over here). That file had zero importers left after the auth-store split and
 * is deleted by the legacy-transport deletion.
 */
export function writeClanCookie(clanId: string): void {
  if (typeof document === 'undefined') return
  document.cookie = `${CLAN_COOKIE}=${encodeURIComponent(clanId)}; ${clanCookieAttributes()}`
  notifyClanCookieChanged()
}

export function clearClanCookie(): void {
  if (typeof document === 'undefined') return
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0; samesite=lax`
  notifyClanCookieChanged()
}

/**
 * A plain, non-reactive read of the active clan id, for callers that are not
 * React components — `useAuth`'s `syncAuthContext` needs the value once per
 * call, not a subscription, and the legacy
 * `src/infrastructure/http/request-context.ts` needs it without importing a
 * hook into a function that also runs when `window` is undefined.
 */
export function readCurrentClanId(): string | null {
  return parseClanCookie(readCookie(CLAN_COOKIE))
}

/**
 * Reactive read of the active clan for a client component. Wiring
 * this into a TanStack Query key is what makes "switch clan" change what a
 * query returns without a page reload: `writeClanCookie` notifies every
 * subscriber, which re-renders with the new clan id, which changes the query
 * key. A real page reload (or this hook's own first render) reads the cookie
 * directly rather than any store — the same fact the server can also read —
 * which is what makes the selection survive a reload.
 */
export function useCurrentClanId(): string | null {
  return useSyncExternalStore(subscribeToClanCookieChanges, readCurrentClanId, () => null)
}

/**
 * Request context in the browser.
 *
 * Locale comes from the URL rather than a store: with localePrefix 'always' the
 * path is the authoritative locale, and it is correct on the very first render
 * before any store has hydrated.
 */
export async function getClientRequestContext(): Promise<RequestContext> {
  let accessToken: string | null = null
  try {
    const supabase = createClientOrNull()
    if (supabase) {
      const { data } = await supabase.auth.getSession()
      accessToken = data.session?.access_token ?? null
    }
  } catch {
    accessToken = null
  }

  return {
    locale: localeFromPathname(window.location.pathname),
    clanId: parseClanCookie(readCookie(CLAN_COOKIE)),
    accessToken,
  }
}

/**
 * The one browser-wide `refreshAuth`, for `apiFetch`'s 401 retry. ADR-061 § 6.
 *
 * Module-level, so every caller in the tab shares one single flight: when a token expires, every
 * request in flight 401s at once, and they must collapse onto one `refreshSession()` rather than
 * rotate the refresh token once each. Built per hook call instead, two screens would each refresh.
 *
 * Resolves the refreshed context, or `null` when there is no Supabase client or Supabase refuses
 * the refresh. `null` tells `apiFetch` to surface the 401 rather than retry, and signing out is the
 * screen's decision, not transport's. A successful refresh also reaches every
 * `useClientRequestContext` through Supabase's `TOKEN_REFRESHED`, so the request after the retry
 * carries the new token too.
 */
export const refreshAuth: () => Promise<RequestContext | null> = createSingleFlight(async () => {
  try {
    const supabase = createClientOrNull()
    if (!supabase) return null
    const { data, error } = await supabase.auth.refreshSession()
    const accessToken = data.session?.access_token
    if (error || !accessToken) return null
    return {
      locale: localeFromPathname(window.location.pathname),
      clanId: readCurrentClanId(),
      accessToken,
    }
  } catch {
    return null
  }
})

/**
 * `refreshAuth`, resolving a context that carries `clanId` rather than whatever the cookie names
 * when the refresh lands. A retry then goes to the clan its first attempt went to, and a surface
 * that sends no clan sends none on the retry either. Every caller still shares the one refresh.
 */
export function refreshAuthFor(clanId: string | null): () => Promise<RequestContext | null> {
  return async () => {
    const refreshed = await refreshAuth()
    return refreshed && { ...refreshed, clanId }
  }
}

export interface ClientRequestContextOptions {
  /**
   * False for a surface that must send no `X-Current-Clan-Id` whatever the cookie says, such as
   * the invitee surface, whose contract forbids it. The context and the context `refreshAuth`
   * resolves both leave the clan out.
   */
  clanScoped?: boolean
}

export interface ClientRequestContext {
  context: RequestContext
  /** False until the first read of the Supabase session has finished. Gate requests on it. */
  ready: boolean
  /** The browser-wide `refreshAuth` above, through `refreshAuthFor` this hook's clan. */
  refreshAuth: () => Promise<RequestContext | null>
}

interface BrowserSession {
  locale: RequestContext['locale']
  accessToken: RequestContext['accessToken']
}

/**
 * The request context for a client component. Every slice reads this one, and passes `context`
 * and `refreshAuth` to its hooks. ADR-061 § 6.
 *
 * - **The clan** is `useCurrentClanId()`, so a clan switch re-renders with the new id and a query
 *   key built from it refetches.
 * - **The locale** is the URL's first segment, read on mount, as `getClientRequestContext` reads it.
 * - **The access token follows Supabase.** It is read once from `getSession()` and then from every
 *   auth event, so `TOKEN_REFRESHED`, whether from Supabase's own timer or from `refreshAuth`,
 *   reaches the next request without a remount. Once an event has arrived, the first read's answer
 *   is dropped, since it may predate the event.
 */
export function useClientRequestContext(
  options: ClientRequestContextOptions = {},
): ClientRequestContext {
  const { clanScoped = true } = options
  const cookieClanId = useCurrentClanId()
  const clanId = clanScoped ? cookieClanId : null
  const [session, setSession] = useState<BrowserSession | null>(null)

  useEffect(() => {
    const locale = localeFromPathname(window.location.pathname)
    let active = true
    let heardEvent = false
    const apply = (accessToken: string | null) => {
      if (active) setSession({ locale, accessToken })
    }

    let listener: { data: { subscription: { unsubscribe: () => void } } } | undefined
    let firstRead: Promise<string | null>
    try {
      // With no Supabase configured there is no session to read and no event to hear.
      const supabase = createClientOrNull()
      listener = supabase?.auth.onAuthStateChange((_event, changed) => {
        heardEvent = true
        apply(changed?.access_token ?? null)
      })
      firstRead = supabase
        ? supabase.auth.getSession().then(({ data }) => data.session?.access_token ?? null)
        : Promise.resolve(null)
    } catch {
      // A client that cannot be built reads as signed out, as `getClientRequestContext` reads it,
      // rather than leaving `ready` false for good.
      firstRead = Promise.resolve(null)
    }
    firstRead.then(
      (accessToken) => {
        if (!heardEvent) apply(accessToken)
      },
      () => {
        if (!heardEvent) apply(null)
      },
    )

    return () => {
      active = false
      listener?.data.subscription.unsubscribe()
    }
  }, [])

  const refreshAuthForClan = useMemo(() => refreshAuthFor(clanId), [clanId])

  return {
    context: {
      locale: session?.locale ?? 'vi',
      clanId,
      accessToken: session?.accessToken ?? null,
    },
    ready: session !== null,
    refreshAuth: refreshAuthForClan,
  }
}
