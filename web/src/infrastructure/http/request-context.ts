import type { RequestContext } from '@/domain/shared/types'
import { readCurrentClanId } from '@/shared/http/context.client'
import { localeFromPathname } from '@/shared/http/request-context'

/**
 * Centralized request context retrieval so adapters/interceptors stay consistent.
 *
 * Two reads, one per fact, and both are ones the server can make too. The clan is the
 * `current_clan_id` cookie, through `readCurrentClanId`. The locale is the URL's first segment,
 * as `getClientRequestContext` reads it, because `localePrefix` is `'always'`.
 *
 * #183 removed the last two fallbacks. The zustand store's `user.clan_id` went with the store,
 * and `localStorage['preferred_locale']` went because nothing writes it any more: the legacy
 * `useAuth` was its only writer.
 */
export function getRequestContext(): RequestContext {
  if (typeof window === 'undefined') {
    return { locale: 'vi' }
  }

  return {
    locale: localeFromPathname(window.location.pathname),
    currentClanId: readCurrentClanId() ?? undefined,
  }
}
