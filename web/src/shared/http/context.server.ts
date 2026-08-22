import 'server-only'

import { cookies } from 'next/headers'
import { createClient } from '@/lib/supabase/server'
import {
  CLAN_COOKIE,
  LOCALE_COOKIE,
  normalizeLocale,
  parseClanCookie,
  type RequestContext,
} from './request-context'

/**
 * Request context inside a Server Component or route handler.
 *
 * The clan id comes from a cookie because there is no localStorage here — this
 * is the reason the clan selection moved to a cookie at all.
 */
export async function getServerRequestContext(): Promise<RequestContext> {
  const store = await cookies()

  let accessToken: string | null = null
  try {
    const supabase = await createClient()
    const { data } = await supabase.auth.getSession()
    accessToken = data.session?.access_token ?? null
  } catch {
    // Supabase env vars missing (local dev) or no session — anonymous context.
    accessToken = null
  }

  return {
    locale: normalizeLocale(store.get(LOCALE_COOKIE)?.value),
    clanId: parseClanCookie(store.get(CLAN_COOKIE)?.value),
    accessToken,
  }
}
