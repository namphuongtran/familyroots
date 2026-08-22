import createMiddleware from 'next-intl/middleware'
import { createServerClient } from '@supabase/ssr'
import { type NextRequest, NextResponse } from 'next/server'
import { routing } from './i18n/routing'
import { CLAN_COOKIE, parseClanCookie } from './shared/http/request-context'

const intlMiddleware = createMiddleware(routing)

/**
 * `/verify-email` and `/clan-suspended` joined this list with the three blocked-state
 * screens (S-026). Both are reached by an immediate client-side `router.push`/`.replace`
 * right after a call made with the session that was already in the browser — `/verify-email`
 * would be, if the live sign-in path called the backend endpoint that raises
 * `email_not_verified` (see `components/auth/VerifyEmailScreen.tsx`'s comment for why it does
 * not yet), and `/clan-suspended` already is, from `select-clan/page.tsx` on a real
 * `clan_suspended` response. `/pending-approval` is public for the identical reason: a
 * server-side session check run milliseconds after a client-side sign-in can race the cookie
 * Supabase's SSR helper just set, and public here means that race can never produce a
 * redirect-to-login loop on a screen the user is legitimately allowed to see.
 */
const PUBLIC_ROUTES = [
  '/login',
  '/register',
  '/auth/callback',
  '/pending-approval',
  '/verify-email',
  '/clan-suspended',
]

/**
 * First path segment (after the locale prefix) of every route under the
 * `(dashboard)` group — `find web/src/app/[locale] -maxdepth 2`, 2026-08-22.
 * `select-clan` itself, `platform/*` and `backoffice/*` are deliberately not
 * here: the first is the picker this list redirects to, and the other two
 * are cross-clan super-admin surfaces (`docs/architecture/multi-tenancy.md`),
 * not clan-scoped.
 */
const CLAN_SCOPED_SEGMENTS = ['dashboard', 'documents', 'events', 'members', 'tree', 'admin']

export async function middleware(request: NextRequest) {
  // Run intl middleware first so locale-prefixed routes resolve
  const intlResponse = intlMiddleware(request)

  const { pathname } = request.nextUrl

  // Strip locale prefix to test route protection
  const strippedPath = pathname.replace(/^\/(?:vi|en|zh|fr)/, '') || '/'

  // Allow public auth routes through without a session check
  if (PUBLIC_ROUTES.some(r => strippedPath.startsWith(r))) {
    return intlResponse
  }

  // Dashboard / protected routes require an active session
  if (!strippedPath.startsWith('/(')) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

    // Skip auth check if Supabase env vars are not configured
    if (!supabaseUrl || !supabaseKey) {
      return intlResponse
    }

    const supabaseResponse = NextResponse.next({ request })

    const supabase = createServerClient(
      supabaseUrl,
      supabaseKey,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll()
          },
          setAll(cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]) {
            cookiesToSet.forEach(({ name, value, options }) => {
              request.cookies.set(name, value)
              supabaseResponse.cookies.set(name, value, options as Parameters<typeof supabaseResponse.cookies.set>[2])
              intlResponse.cookies.set(name, value, options as Parameters<typeof intlResponse.cookies.set>[2])
            })
          },
        },
      },
    )

    const { data: { session } } = await supabase.auth.getSession()

    if (!session) {
      const locale = pathname.split('/')[1] || 'vi'
      const loginUrl = new URL(`/${locale}/login`, request.url)
      return NextResponse.redirect(loginUrl)
    }

    // A clan-scoped route needs an active clan before it renders anything,
    // so it never gets the chance to send a clan-scoped request with no
    // `X-Current-Clan-Id` and find out from a backend 400. Missing and
    // unparseable are the same case here: both mean "no clan selected"
    // (`parseClanCookie`, `shared/http/request-context.ts`).
    const firstSegment = strippedPath.split('/')[1]
    if (
      CLAN_SCOPED_SEGMENTS.includes(firstSegment) &&
      parseClanCookie(request.cookies.get(CLAN_COOKIE)?.value) === null
    ) {
      const locale = pathname.split('/')[1] || 'vi'
      return NextResponse.redirect(new URL(`/${locale}/select-clan`, request.url))
    }
  }

  return intlResponse
}

export const config = {
  matcher: [
    '/((?!api|_next/static|_next/image|favicon.ico|icons|images|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
