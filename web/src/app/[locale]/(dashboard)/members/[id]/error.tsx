'use client'

import { useTranslations } from 'next-intl'
import { PersonsErrorState } from '@/features/persons'
import { useReportError } from '@/shared/telemetry/useReportError'

/**
 * Next's route-segment error boundary for the detail screen. `person_not_found`
 * is handled inline by `page.tsx` and never reaches here — this only ever
 * catches a transport failure (network, timeout, a non-404 `ApiError`), so
 * `reset()` retrying the same `getPerson` call is the correct next step
 * (`T-17`).
 */
export default function MemberDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useReportError(error)
  const t = useTranslations('member')
  return <PersonsErrorState title={t('error_title')} onRetry={reset} />
}
