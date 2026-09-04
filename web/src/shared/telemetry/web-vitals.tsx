'use client'

import { useReportWebVitals } from 'next/web-vitals'
import { logger } from './logger'
import { redactInvitationToken } from './redact'

/**
 * Field measurement of how the app behaves on real devices and networks.
 *
 * This is the evidence base for the age-friendly UX work: LCP and INP on an
 * older phone over a weak connection are the numbers that decide whether the
 * design is actually usable, rather than whether it looks fast on a laptop.
 *
 * `route` is redacted, added by the invitation page. This is the app's own log and its only
 * analytics call, it is mounted on every locale route
 * (`app/[locale]/layout.tsx:40`), and it used to pass `window.location.pathname`
 * through verbatim. On `/{locale}/invitations/{token}` that pathname is a bearer
 * credential (`docs/contracts/rest-invitations-api.md:74`), so every Web Vitals
 * metric — several per page view — would have written an invitation token to the
 * console. Measured before the fix on 2026-08-26; see
 * `redact.ts` for the rule and `web-vitals.test.tsx` for the reading.
 */
export function WebVitalsReporter() {
  useReportWebVitals((metric) => {
    logger.info('web-vitals', {
      metric: metric.name,
      value: Math.round(metric.value),
      rating: metric.rating,
      route:
        typeof window === 'undefined' ? undefined : redactInvitationToken(window.location.pathname),
    })
  })
  return null
}
