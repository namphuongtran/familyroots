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
  /**
   * Seed S-084. The invitation route's path carries a bearer credential: the token
   * "is the only thing that decides which clan the caller is granted a role in"
   * (`docs/contracts/rest-invitations-api.md:74`).
   *
   * **This header, and not the page's `metadata.referrer`, is what actually stops
   * the token leaking — measured, not assumed.** The route also exports
   * `referrer: 'no-referrer'`, which Next.js renders as
   * `<meta name="referrer" content="no-referrer">`. That fixes a *navigation* out of
   * the page, and `e2e/invitation-accept.spec.ts` reads `document.referrer` back as
   * the empty string to prove it. It does **not** fix the page's own subresources:
   * Next.js streams `<link rel="preload">` for its chunks before the metadata block,
   * so the document has no referrer policy yet when the browser starts fetching
   * them. Measured 2026-08-26 with the meta tag in place and this header absent, on
   * two runs: 31 requests and then 30 requests left the browser carrying
   * `Referer: http://127.0.0.1:3100/vi/invitations/<token>`, every one of them a
   * `/_next/*` asset. The count is the dev server's chunk count and is not stable
   * between runs; what is stable is that it is not zero.
   *
   * An HTTP response header applies from the document's first byte, so it covers
   * those too. Both are kept: the header is the mechanism, the meta tag is what
   * still holds if a proxy or a static export strips the header.
   */
  async headers() {
    return [
      {
        // `:locale` rather than a literal, because every route is locale-prefixed
        // (`src/i18n/routing.ts`, `localePrefix: 'always'`), and all four locales
        // reach the same page.
        source: '/:locale/invitations/:token',
        headers: [{ key: 'Referrer-Policy', value: 'no-referrer' }],
      },
    ]
  },
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
