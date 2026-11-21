import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'

/**
 * The site footer (#333). It carries the one link every page owes the reader: the privacy notice.
 * Presentational, so it renders in the `[locale]` layout without a client boundary.
 */
export function SiteFooter() {
  const t = useTranslations('privacy')
  const locale = useLocale()
  return (
    <footer className="border-border text-muted-foreground border-t px-4 py-4 text-center text-xs">
      <Link href={`/${locale}/privacy`} className="text-primary hover:underline">
        {t('footer_link')}
      </Link>
    </footer>
  )
}
