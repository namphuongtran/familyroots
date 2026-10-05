import { guardClanRoute } from '@/features/auth/index.server'

/**
 * Admits a member whose role in the active clan holds `viewPendingUsers`
 * (`docs/architecture/rbac.md`, "View pending users"), and sends anyone else to the dashboard (#186,
 * ADR-061 § 4). The page is a client component, so this layout is its guard.
 */
export default async function AdminUsersLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  await guardClanRoute(locale, 'viewPendingUsers')

  return children
}
