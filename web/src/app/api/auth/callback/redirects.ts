import { routing, type Locale } from '@/i18n/routing'

const DEFAULT_NEXT = `/${routing.defaultLocale}/dashboard`

/**
 * Where `/api/auth/callback` sends the browser, from the `next` that `signInWithOAuth` put on
 * the provider's return URL (`/${locale}/dashboard`).
 *
 * - `success` is `next` when it is a path on this origin, and the default dashboard otherwise.
 *   A `next` such as `@evil.com` would turn the route's `${origin}${next}` into
 *   `https://<origin>@evil.com`, and `//evil.com` or `/\evil.com` is protocol-relative.
 * - `failure` is the login page in `next`'s locale (#290). It used to be `/vi/login` for every
 *   reader.
 */
export function callbackRedirects(nextParam: string | null): { success: string; failure: string } {
  const success = isSameOriginPath(nextParam) ? nextParam : DEFAULT_NEXT
  const locale = localeOf(success)
  return { success, failure: `/${locale}/login?error=auth_callback_failed` }
}

function isSameOriginPath(value: string | null): value is string {
  return value !== null && value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')
}

function localeOf(path: string): Locale {
  const segment = path.split('/')[1]
  return routing.locales.find((locale) => locale === segment) ?? routing.defaultLocale
}
