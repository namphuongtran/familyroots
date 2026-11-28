'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'

/** The app's footer: today it carries the privacy notice link (#333). */
export function SiteFooter() {
  const t = useTranslations('privacy')
  const locale = useLocale()

  return (
    <footer className="bg-muted text-muted-foreground px-4 py-3 text-center text-xs">
      <Link href={`/${locale}/privacy`} className="text-primary hover:underline">
        {t('link')}
      </Link>
    </footer>
  )
}
