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

/**
 * `clan_id` is a UUID everywhere in the backend (cast `::uuid` throughout
 * `docs/architecture/data-model.md`), so a cookie value that is not one of
 * these shapes did not come from a legitimate clan selection. Middleware and
 * both context builders route a value that fails this the same way they route
 * a missing cookie: as "no clan selected", rather than forwarding garbage as
 * `X-Current-Clan-Id` and letting the backend reject it.
 */
const CLAN_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * The single reader of the `current_clan_id` cookie value. Returns null for
 * both "not set" and "set but not a UUID" — callers that need to tell those
 * two apart (there are none today) must inspect the raw cookie themselves.
 */
export function parseClanCookie(raw: string | null | undefined): string | null {
  if (!raw) return null
  return CLAN_ID_PATTERN.test(raw) ? raw : null
}

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
