import type { RequestContext } from '@/domain/shared/types'
import { useAuthStore } from '@/store/auth.store'

const SUPPORTED_LOCALES = new Set(['vi', 'en', 'zh', 'fr'])

function normalizeLocale(raw: string | null | undefined): RequestContext['locale'] {
  if (raw && SUPPORTED_LOCALES.has(raw)) {
    return raw as RequestContext['locale']
  }
  return 'vi'
}

/**
 * Centralized request context retrieval so adapters/interceptors stay consistent.
 */
export function getRequestContext(): RequestContext {
  if (typeof window === 'undefined') {
    return { locale: 'vi' }
  }

  const locale = normalizeLocale(localStorage.getItem('preferred_locale'))

  const authState = useAuthStore.getState()
  const currentClanId =
    authState.currentClanId ??
    authState.user?.clan_id ??
    localStorage.getItem('current_clan_id') ??
    undefined

  return {
    locale,
    currentClanId,
  }
}