import { guardClanRoute } from '@/features/auth/index.server'

/**
 * Admits a member whose role in the active clan holds `editClanSettings`
 * (`docs/architecture/rbac.md`, "Edit clan settings"), and sends anyone else to the dashboard (#186,
 * ADR-061 § 4). The page is a client component, so this layout is its guard.
 */
export default async function AdminClanLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  await guardClanRoute(locale, 'editClanSettings')

  return children
}
