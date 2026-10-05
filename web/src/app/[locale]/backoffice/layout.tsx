import { guardClanRoute } from '@/features/auth/index.server'
import { BackofficeSidebar } from '@/components/backoffice/BackofficeSidebar'

/**
 * Backoffice layout — completely separate from the user-facing (dashboard).
 * Access needs `viewPendingUsers` in the active clan (#186, ADR-061 § 4). A super_admin with no
 * such membership is sent away like anyone else: the backend's clan checks give the role no bypass.
 *
 * Route group: src/app/[locale]/(backoffice)/
 * URL prefix:  /[locale]/backoffice/
 *
 * This section is the right place for:
 *   - Managing ALL members across a clan (CRUD)
 *   - Reviewing and approving pending registrations
 *   - Configuring clan settings, events, documents
 *   - Viewing audit logs
 *   - (super_admin only) Cross-clan platform operations → platform/ route
 */
export default async function BackofficeLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  await guardClanRoute(locale, 'viewPendingUsers')

  // Below `lg` the sidebar is a top bar and a drawer; at `lg` and up it is an in-flow sibling of
  // `main` in one flex row, and `main` takes the rest of the row from `min-w-0 flex-1`. No `ml-*`
  // matches the rail's width: that pairing, with a `fixed` rail, is what left `main` zero pixels
  // wide at 320px and 200% text (#174).
  return (
    <div className="bg-background min-h-screen lg:flex">
      <BackofficeSidebar locale={locale} />
      <main className="bg-background min-w-0 flex-1">{children}</main>
    </div>
  )
}
