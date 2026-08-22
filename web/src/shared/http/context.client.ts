'use client'

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
 *   what the legacy writer (`src/infrastructure/auth/clan-selection-storage.ts`)
 *   already ships.
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
 * Selecting a clan writes this cookie. Nothing calls this yet — the
 * `select-clan` flow still writes through the legacy
 * `persistCurrentClanId` (same cookie name, compatible attributes), and S-025
 * is what rewires it onto the spine. This is the canonical writer that S-025
 * adopts, kept here so the attributes above are decided in exactly one place.
 */
export function writeClanCookie(clanId: string): void {
  if (typeof document === 'undefined') return
  document.cookie = `${CLAN_COOKIE}=${encodeURIComponent(clanId)}; ${clanCookieAttributes()}`
}

export function clearClanCookie(): void {
  if (typeof document === 'undefined') return
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0; samesite=lax`
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
