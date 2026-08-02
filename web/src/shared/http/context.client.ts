'use client'

import { createClientOrNull } from '@/lib/supabase/client'
import { CLAN_COOKIE, localeFromPathname, type RequestContext } from './request-context'

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
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
    clanId: readCookie(CLAN_COOKIE),
    accessToken,
  }
}
