'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'

/**
 * The 404 for every path under a locale (#366). It renders inside the locale layout, so the
 * message provider is in scope. The link goes to the dashboard; a visitor with no session is sent
 * on to login by the middleware.
 */
export default function LocaleNotFound() {
  const t = useTranslations('notFound')
  const locale = useLocale()

  return (
    <div className="bg-background flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="text-foreground text-xl font-semibold">{t('title')}</h1>
      <p className="text-foreground text-sm">{t('body')}</p>
      <Link
        href={`/${locale}/dashboard`}
        className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-4 py-2 text-sm font-medium focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
      >
        {t('back')}
      </Link>
    </div>
  )
}
