import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'
import { withSentryConfig } from '@sentry/nextjs'

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts')

const nextConfig: NextConfig = {
  output: 'standalone',
  // S-042: `web/playwright.config.ts` boots a second `next dev` instance, deliberately without
  // the two `NEXT_PUBLIC_SUPABASE_*` variables, so `e2e/supabase-banner.spec.ts` can measure the
  // missing-Supabase banner at all. Next.js refuses a second `next dev` that shares a `distDir`
  // (`node_modules/next/dist/server/lib/router-utils/setup-dev-bundler.js`, the
  // `experimental.lockDistDir` lock — "Another next dev server is already running", verified
  // 2026-08-22), so the second instance needs its own. Unset for every other invocation —
  // `pnpm dev`, `pnpm build`, and the primary e2e server all keep using `.next`.
  distDir: process.env.PLAYWRIGHT_SECOND_DIST_DIR || '.next',
  // Moved out of `experimental` in Next.js 15+ (Next.js 16 uses top-level key)
  serverExternalPackages: [],
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '*.supabase.co',
        pathname: '/storage/v1/object/**',
      },
      {
        protocol: 'https',
        hostname: '*.supabase.in',
        pathname: '/storage/v1/object/**',
      },
    ],
  },
}

// Sentry outermost: it wraps the assembled config, next-intl's plugin included.
export default withSentryConfig(withNextIntl(nextConfig), {
  silent: true,
  // Source maps are uploaded only when the auth token is present, so a local
  // build never fails for want of Sentry credentials.
  authToken: process.env.SENTRY_AUTH_TOKEN,
})
