import { notFound } from 'next/navigation'

/**
 * Next renders `[locale]/not-found.tsx` only when a route calls `notFound()`. An unmatched path
 * under a locale matches no route, so it would fall through to Next's English default (#366).
 * This catch-all matches it and hands it to the localized 404.
 */
export default function UnknownPathPage() {
  notFound()
}
