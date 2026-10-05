'use client'

import { useTranslations } from 'next-intl'

/**
 * The error boundary for every route under a locale, and the one a layout's error reaches: an
 * `error.tsx` beside a layout wraps that layout's children, not the layout itself. So this is
 * where a failed session read in the server guard lands, from the `(dashboard)`, `backoffice` or
 * `platform` layout (#186). It offers the retry the `(dashboard)` layout's client redirect used to.
 *
 * `unstable_retry` re-fetches the segment, which `reset` does not, and a server error only
 * recovers by being fetched again. `error.message` is not shown: a production build replaces a
 * server error's message before it reaches the browser.
 */
export default function LocaleError({ unstable_retry }: { unstable_retry: () => void }) {
  const t = useTranslations('common')

  return (
    <div className="bg-background flex min-h-screen flex-col items-center justify-center gap-3 px-4">
      <p role="alert" className="text-foreground text-sm">
        {t('error')}
      </p>
      <button
        type="button"
        onClick={() => unstable_retry()}
        className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-4 py-2 text-sm font-medium focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
      >
        {t('retry')}
      </button>
    </div>
  )
}
