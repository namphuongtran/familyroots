'use client'

import { useEffect } from 'react'
import * as Sentry from '@sentry/nextjs'

/**
 * Reports the error an `error.tsx` boundary caught, once per error, from an effect (#366). A render
 * error in the browser never reaches `onRequestError`, which is server-only. Nothing is attached
 * to the event: `instrumentation-client.ts` owns what the SDK may send (`sendDefaultPii: false`
 * and the invitation-token scrub), and a tag or extra added here would sit outside it.
 */
export function useReportError(error: Error & { digest?: string }) {
  useEffect(() => {
    Sentry.captureException(error)
  }, [error])
}
