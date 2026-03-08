import createMiddleware from 'next-intl/middleware'
import { createServerClient } from '@supabase/ssr'
import { type NextRequest, NextResponse } from 'next/server'
import { routing } from './i18n/routing'

const intlMiddleware = createMiddleware(routing)

const PUBLIC_ROUTES = [
  '/login',
  '/register',
  '/auth/callback',
  '/pending-approval',
]

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
  }

  return intlResponse
}

export const config = {
  matcher: [
    '/((?!api|_next/static|_next/image|favicon.ico|icons|images|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
