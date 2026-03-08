import { requireRole } from '@/lib/utils/with-role'
import { BackofficeSidebar } from '@/components/backoffice/BackofficeSidebar'

/**
 * Backoffice layout — completely separate from the user-facing (dashboard).
 * Access is restricted to `admin` and `super_admin` roles.
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
  // Hard server-side gate — redirect to /[locale]/dashboard if insufficient role
  await requireRole(['admin', 'super_admin'], locale)

  return (
    <div className="flex min-h-screen bg-gray-900">
      <BackofficeSidebar locale={locale} />
      <main className="ml-60 flex-1 min-h-screen overflow-y-auto bg-gray-50">
        {children}
      </main>
    </div>
  )
}
