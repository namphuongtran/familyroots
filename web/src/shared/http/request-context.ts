/**
 * What a request needs to know about who is asking, independent of runtime.
 *
 * Deliberately a plain value passed into apiFetch rather than something read
 * from a global: the same repository function then runs unchanged inside a
 * Server Component and in the browser, and transport tests need no mocking of
 * cookies, stores, or window.
 */

import { DEFAULT_LOCALE, SUPPORTED_LOCALES, type LocaleCode } from '@/domain/shared/types'

export interface RequestContext {
  locale: LocaleCode
  /** null when the user has not selected a clan yet. */
  clanId: string | null
  /** null when unauthenticated; public endpoints still work. */
  accessToken: string | null
}

/** Readable by the server, unlike the localStorage key it replaces. */
export const CLAN_COOKIE = 'current_clan_id'
export const LOCALE_COOKIE = 'preferred_locale'

export function normalizeLocale(raw: string | null | undefined): LocaleCode {
  if (!raw) return DEFAULT_LOCALE
  const base = raw.trim().toLowerCase().split('-')[0]
  return (SUPPORTED_LOCALES as readonly string[]).includes(base)
    ? (base as LocaleCode)
    : DEFAULT_LOCALE
}

/** localePrefix is 'always', so the first path segment is the locale. */
export function localeFromPathname(pathname: string): LocaleCode {
  return normalizeLocale(pathname.split('/')[1])
}
