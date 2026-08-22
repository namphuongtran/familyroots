'use client'

import { useSyncExternalStore } from 'react'
import { createClientOrNull } from '@/lib/supabase/client'
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
 * without a page reload (S-025).
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
 * S-024 through S-033 inherit this shape rather than re-deciding it:
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
 *   (`src/infrastructure/auth/clan-selection-storage.ts`, deleted by S-027 once nothing
 *   imported it — S-025 had already moved both real callers off it).
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
 * `syncAuthContext` call this now (S-025) instead of the legacy
 * `persistCurrentClanId` (`src/infrastructure/auth/clan-selection-storage.ts`, same
 * cookie name, compatible attributes, but it also wrote `localStorage.current_clan_id` —
 * deliberately not carried over here). That file had zero importers left after S-025 and
 * is deleted by S-027.
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
 * Reactive read of the active clan for a client component (S-025). Wiring
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
