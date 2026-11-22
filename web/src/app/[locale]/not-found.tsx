import Link from 'next/link'
import { getLocale, getTranslations } from 'next-intl/server'

/**
 * The localized 404 (#366). `/{locale}/dashboard` is the link target: a visitor with no session is
 * sent on to login by the middleware.
 */
export default async function LocaleNotFound() {
  const [t, locale] = await Promise.all([getTranslations('not_found'), getLocale()])

  return (
    <main className="bg-background flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="text-foreground font-serif text-3xl">{t('title')}</h1>
      <p className="text-muted-foreground text-sm">{t('body')}</p>
      <Link
        href={`/${locale}/dashboard`}
        className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-4 py-2 text-sm font-medium focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
      >
        {t('home_link')}
      </Link>
    </main>
  )
}
