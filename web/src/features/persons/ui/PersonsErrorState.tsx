'use client'

import { useTranslations } from 'next-intl'

interface PersonsErrorStateProps {
  /** `title`/`retryLabel` come from the caller's own namespace (`members` for the list, `member` for the detail screen) so each surface's copy stays specific to what failed. */
  title: string
  message?: string | null
  onRetry: () => void
}

/**
 * `T-17`: every error state offers a way forward, never a dead end. Shared
 * by `PersonsList`'s own in-place error branch and both route-level
 * `error.tsx` boundaries (list and detail) — a route boundary's `reset()`
 * and a query's `refetch()` are both just "try again", so one component
 * covers both call sites.
 */
export function PersonsErrorState({ title, message, onRetry }: PersonsErrorStateProps) {
  const t = useTranslations('member')
  return (
    <div className="bg-muted flex flex-col items-center gap-3 rounded-2xl p-8 text-center">
      <p className="text-foreground text-sm font-medium">{title}</p>
      {message && <p className="text-muted-foreground text-sm">{message}</p>}
      <button
        type="button"
        onClick={onRetry}
        className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-5 py-2 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
      >
        {t('retry')}
      </button>
    </div>
  )
}
