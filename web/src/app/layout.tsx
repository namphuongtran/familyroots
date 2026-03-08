import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'FamilyRoots',
  description: 'Vietnamese family genealogy platform',
}

// Root layout — minimal wrapper. The [locale] segment carries all real providers.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children
}

