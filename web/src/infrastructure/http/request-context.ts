import type { RequestContext } from '@/domain/shared/types'
import { readCurrentClanId } from '@/shared/http/context.client'
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
 *
 * The three-way read this used to do — `useAuthStore.currentClanId`, then
 * `user.clan_id`, then `localStorage.current_clan_id` — is gone (S-025): the
 * store no longer holds a clan id at all, and nothing here reads
 * `localStorage.current_clan_id`. The `current_clan_id` cookie (S-023) is the
 * one source now, read through `readCurrentClanId`; `user.clan_id` stays as a
 * fallback for the moment before the cookie is written on first sync.
 */
export function getRequestContext(): RequestContext {
  if (typeof window === 'undefined') {
    return { locale: 'vi' }
  }

  const locale = normalizeLocale(localStorage.getItem('preferred_locale'))
  const currentClanId = readCurrentClanId() ?? useAuthStore.getState().user?.clan_id ?? undefined

  return {
    locale,
    currentClanId,
  }
}
