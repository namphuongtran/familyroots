import { NextIntlClientProvider } from 'next-intl'
import { getMessages, getTranslations } from 'next-intl/server'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { Providers } from '@/components/providers'
import { routing, type Locale } from '@/i18n/routing'
import { WebVitalsReporter } from '@/shared/telemetry/web-vitals'

/**
 * The document title and description, in the route's locale (#197). They were one static
 * Vietnamese pair, so every reader's tab and search snippet read Vietnamese. A page that sets its
 * own title, such as `backoffice/dashboard/page.tsx`, still overrides this one.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: 'metadata' })
  return {
    // Not copy: the product name, one literal in every locale. Only the tagline is translated.
    title: `FamilyRoots – ${t('tagline')}`,
    description: t('description'),
  }
}

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }))
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  if (!routing.locales.includes(locale as Locale)) notFound()

  const messages = await getMessages()

  /*
    No wrapper `<div>` here: `<html>`/`<body>` live in `web/src/app/layout.tsx`
    (see the comment there — this layout cannot own the document element
    because `app/page.tsx` and `app/api/*` share the same root layout outside
    this segment). `antialiased` is already applied to `body` by
    `globals.css`'s `@layer base` rule, so a second copy on a `<div>` here was
    dead weight, not a fallback. See the `<html lang>` fix.
  */
  return (
    <>
      <WebVitalsReporter />
      <NextIntlClientProvider locale={locale} messages={messages}>
        <Providers>{children}</Providers>
      </NextIntlClientProvider>
    </>
  )
}
