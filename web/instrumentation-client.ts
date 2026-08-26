import * as Sentry from '@sentry/nextjs'
import { redactInvitationTokensDeep } from '@/shared/telemetry/redact'

/**
 * Drops an invitation token out of everything this SDK is about to send.
 *
 * Added by seed S-084. The browser SDK records a breadcrumb for every `fetch` and
 * every router navigation, each carrying the URL, and puts the page URL on the
 * event itself. Two URLs in this app carry a bearer credential: the browser route
 * `/{locale}/invitations/{token}` and the accept call
 * `POST /api/v1/invitations/{token}/accept`. The token "is the only thing that
 * decides which clan the caller is granted a role in"
 * (`docs/contracts/rest-invitations-api.md:74`), so a Sentry issue carrying one is
 * a credential in a third-party system that anybody with issue access can replay.
 *
 * Applied to all three hooks rather than only `beforeSend`, because a breadcrumb
 * is attached to a *later* event: without `beforeBreadcrumb`, an error thrown ten
 * minutes after the invitation page still ships that page's navigation and fetch
 * breadcrumbs.
 *
 * **Fails closed.** If the scrub itself throws, the event is dropped (`return
 * null`) rather than sent unscrubbed. Losing telemetry is recoverable; leaking a
 * credential is not.
 */
function scrub<T>(payload: T): T | null {
  try {
    return redactInvitationTokensDeep(payload)
  } catch {
    return null
  }
}

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_APP_ENV ?? 'development',
  tracesSampleRate: process.env.NEXT_PUBLIC_APP_ENV === 'production' ? 0.1 : 1.0,
  // Only propagate trace headers to our own API. Without this the SDK would
  // attach them to third-party hosts too, which leaks internal ids.
  tracePropagationTargets: [process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'],
  sendDefaultPii: false,
  beforeBreadcrumb: (breadcrumb) => scrub(breadcrumb),
  beforeSend: (event) => scrub(event),
  beforeSendTransaction: (event) => scrub(event),
})

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart
