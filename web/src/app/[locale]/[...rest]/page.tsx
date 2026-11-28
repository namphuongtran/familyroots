import { notFound } from 'next/navigation'

/**
 * Catches every path under a locale that no other route claims, so it renders
 * `[locale]/not-found.tsx` inside the locale layout instead of Next's default English 404 (#366).
 */
export default function UnknownPath() {
  notFound()
}
