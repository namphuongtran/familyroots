'use client'

import * as Sentry from '@sentry/nextjs'
import { useEffect } from 'react'

/**
 * The last boundary, for an error in the root layout or the locale layout (#366). It replaces the
 * root layout, so it renders its own `<html>` and cannot use next-intl: the copy is a fixed
 * Vietnamese and English pair. The error is reported as-is; `instrumentation-client.ts` decides
 * what the event may carry.
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string }
  unstable_retry: () => void
}) {
  useEffect(() => {
    Sentry.captureException(error)
  }, [error])

  return (
    <html lang="vi">
      <body>
        <div style={{ padding: '2rem', textAlign: 'center', fontFamily: 'sans-serif' }}>
          <p role="alert">Đã xảy ra lỗi.</p>
          <p>Something went wrong.</p>
          <button type="button" onClick={() => unstable_retry()}>
            Thử lại / Retry
          </button>
        </div>
      </body>
    </html>
  )
}
