/**
 * Security headers sent on every web response (#319), built once and wired in
 * `next.config.ts`'s `headers()`.
 *
 * `script-src` keeps `'unsafe-inline'`: Next.js streams inline bootstrap scripts, and giving them
 * a nonce needs a per-request header from middleware, which makes every page dynamic and touches
 * every early return in `src/middleware.ts`. `frame-ancestors 'none'` (the clickjacking fix), the
 * origin allow-lists and `object-src 'none'` do not depend on that.
 */

function originOf(value: string | undefined): string | null {
  if (!value) return null
  try {
    return new URL(value).origin
  } catch {
    return null
  }
}

export function buildCsp(env: NodeJS.ProcessEnv = process.env, dev = false): string {
  const connect = new Set<string>([
    "'self'",
    'https://*.supabase.co',
    'wss://*.supabase.co',
    'https://*.supabase.in',
    'wss://*.supabase.in',
    'https://*.sentry.io',
    'https://*.ingest.sentry.io',
  ])
  for (const raw of [
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000',
    env.NEXT_PUBLIC_API_URL,
  ]) {
    const origin = originOf(raw)
    if (origin) connect.add(origin)
  }
  if (dev) {
    connect.add('ws:')
    connect.add('http://localhost:*')
  }
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://*.supabase.co https://*.supabase.in",
    "font-src 'self' data:",
    `connect-src ${[...connect].join(' ')}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ]
  return directives.join('; ')
}

export function securityHeaders(
  env: NodeJS.ProcessEnv = process.env,
  dev = env.NODE_ENV !== 'production',
): { key: string; value: string }[] {
  const headers = [
    { key: 'Content-Security-Policy', value: buildCsp(env, dev) },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    {
      key: 'Permissions-Policy',
      value:
        'camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=(), interest-cohort=()',
    },
  ]
  if (!dev) {
    headers.push({
      key: 'Strict-Transport-Security',
      value: 'max-age=63072000; includeSubDomains',
    })
  }
  return headers
}
