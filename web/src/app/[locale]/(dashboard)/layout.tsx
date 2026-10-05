import { DashboardShell } from '@/components/layout/DashboardShell'
import { guardClanRoute } from '@/features/auth/index.server'

/**
 * Every `(dashboard)` route admits a member ready in an active clan, and redirects anyone else to
 * where their access state lands (#186, ADR-061 § 3). A page that needs more names its capability
 * in its own guard. The session is read once per request, so a page that calls the guard again
 * for its context sends no second `GET /auth/me`.
 *
 * Until #186 this was a client layout with a redirect effect and a loading spinner, and it wrote
 * the active clan back to the cookie when the cookie named a clan the user had left. The guard
 * sends that case to the clan picker instead, which rewrites the cookie. A failed session read
 * reaches `app/[locale]/error.tsx`, which offers the retry this layout used to.
 */
export default async function DashboardLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  await guardClanRoute(locale)

  return <DashboardShell>{children}</DashboardShell>
}
