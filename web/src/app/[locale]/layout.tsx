import { NextIntlClientProvider } from 'next-intl'
import { getMessages } from 'next-intl/server'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { Providers } from '@/components/providers'
import { routing, type Locale } from '@/i18n/routing'
import { WebVitalsReporter } from '@/shared/telemetry/web-vitals'

export const metadata: Metadata = {
  title: 'FamilyRoots – Gia phả Việt Nam',
  description: 'Nền tảng quản lý gia phả dòng họ Việt Nam',
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
