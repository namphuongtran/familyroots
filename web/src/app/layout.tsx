import type { Metadata } from 'next'
import localFont from 'next/font/local'
import { getLocale } from 'next-intl/server'
import './globals.css'

/*
  The two mandated Arbor Heritage typefaces: Plus Jakarta Sans for headings,
  Manrope for body. Both files are byte-for-byte copies of the ones the Flutter
  app ships, so the two clients render the same shapes. See
  `.claude/rules/tailwind.md` § 8 and the drift test in `./fonts/`.

  Both are variable fonts with a `wght` axis from 200 to 800, so the range is
  declared here and one file covers every weight. The range is not optional:
  Manrope's default instance is ExtraLight (wght 200), so a face declared
  without it renders body text far too thin.

  `next/font/local` generates the family name from the constant it is assigned
  to, so the face is called `manrope` and not `Manrope`. Nothing may name these
  families literally. Read them through the CSS variables below.
*/
const plusJakartaSans = localFont({
  src: './fonts/PlusJakartaSans.ttf',
  variable: '--font-plus-jakarta-sans',
  weight: '200 800',
  display: 'swap',
})

const manrope = localFont({
  src: './fonts/Manrope.ttf',
  variable: '--font-manrope',
  weight: '200 800',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'FamilyRoots',
  description: 'Vietnamese family genealogy platform',
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  /*
    `app/[locale]/layout.tsx` cannot own `<html>` itself: `app/page.tsx` and
    `app/api/*` sit outside the `[locale]` segment and share this same root
    layout, and React does not allow a second, nested `<html>`. `getLocale()`
    reads the locale next-intl's middleware already negotiated for this
    request (from the URL prefix, via a request header — see
    `.claude/rules/tailwind.md` § 7), so it resolves correctly here even though
    this layout sits above the `[locale]` route param. See seed S-022.
  */
  const locale = await getLocale()

  return (
    <html lang={locale} className={`${plusJakartaSans.variable} ${manrope.variable}`}>
      <body>{children}</body>
    </html>
  )
}
