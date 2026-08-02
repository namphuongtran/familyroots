'use client'

import { useReportWebVitals } from 'next/web-vitals'
import { logger } from './logger'

/**
 * Field measurement of how the app behaves on real devices and networks.
 *
 * This is the evidence base for the age-friendly UX work: LCP and INP on an
 * older phone over a weak connection are the numbers that decide whether the
 * design is actually usable, rather than whether it looks fast on a laptop.
 */
export function WebVitalsReporter() {
  useReportWebVitals((metric) => {
    logger.info('web-vitals', {
      metric: metric.name,
      value: Math.round(metric.value),
      rating: metric.rating,
      route: typeof window === 'undefined' ? undefined : window.location.pathname,
    })
  })
  return null
}
