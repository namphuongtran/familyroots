import type { Metadata } from 'next'
import localFont from 'next/font/local'
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plusJakartaSans.variable} ${manrope.variable}`}>
      <body>{children}</body>
    </html>
  )
}
