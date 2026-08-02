import * as Sentry from '@sentry/nextjs'

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_APP_ENV ?? 'development',
  tracesSampleRate: process.env.NEXT_PUBLIC_APP_ENV === 'production' ? 0.1 : 1.0,
  // Only propagate trace headers to our own API. Without this the SDK would
  // attach them to third-party hosts too, which leaks internal ids.
  tracePropagationTargets: [process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'],
  sendDefaultPii: false,
})

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart
