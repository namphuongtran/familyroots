'use client'

import { useReportError } from '@/shared/telemetry/useReportError'

/**
 * Replaces the root layout when it throws (#366), so it owns `<html>` and `<body>` and cannot use
 * the locale layout, next-intl or the stylesheet's providers. The copy is Vietnamese and English
 * literals for that reason, not an oversight: no message file is loaded here.
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string }
  unstable_retry: () => void
}) {
  useReportError(error)

  return (
    <html lang="vi">
      <body>
        <main
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '16px',
            fontFamily: 'system-ui, sans-serif',
            textAlign: 'center',
          }}
        >
          <p role="alert">Đã xảy ra lỗi. / Something went wrong.</p>
          <button type="button" onClick={() => unstable_retry()}>
            Thử lại / Retry
          </button>
        </main>
      </body>
    </html>
  )
}
