'use client'

import { useTranslations } from 'next-intl'
import { PersonsErrorState } from '@/features/persons'

/**
 * Next's route-segment error boundary (`error.tsx` must be a Client
 * Component). Catches whatever `page.tsx` throws — today that is only
 * `getServerAuthContext()`'s own fetch, since `PersonsList` handles its own
 * query error in place rather than throwing. `T-17`: `reset()` gives this a
 * retry rather than a dead end.
 *
 * `error.message` is deliberately not shown: in production Next.js replaces
 * a Server Component error's message with a generic one before it reaches
 * this boundary anyway, and this file has no `error.code` to branch on the
 * way `PersonsList`'s in-place error state does for an `ApiError` — nothing
 * upstream of this boundary is a parsed `ApiError`.
 */
export default function MembersError({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations('members')
  return <PersonsErrorState title={t('error_title')} onRetry={reset} />
}
