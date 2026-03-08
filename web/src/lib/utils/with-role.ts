import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export type AppRole = 'viewer' | 'editor' | 'admin' | 'super_admin'

/**
 * Server-side role guard. Call at the top of a Server Component or layout.
 * Redirects to login if no session, or to /dashboard if the user lacks the
 * required role.
 *
 * @example
 * // In a server layout:
 * const { locale } = await params
 * await requireRole(['admin', 'super_admin'], locale)
 */
export async function requireRole(
  requiredRoles: AppRole | AppRole[],
  locale: string,
): Promise<void> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect(`/${locale}/login`)
  }

  const userRole = user.user_metadata?.clan_role as AppRole | undefined
  const roles = Array.isArray(requiredRoles) ? requiredRoles : [requiredRoles]

  if (!userRole || !roles.includes(userRole)) {
    // Insufficient privilege — send back to user dashboard
    redirect(`/${locale}/dashboard`)
  }
}

/**
 * Returns true if the given role meets the minimum required role level.
 * Role hierarchy (ascending privilege): viewer < editor < admin < super_admin
 */
export function hasMinRole(userRole: AppRole | undefined, minRole: AppRole): boolean {
  const HIERARCHY: Record<AppRole, number> = {
    viewer: 0,
    editor: 1,
    admin: 2,
    super_admin: 3,
  }
  if (!userRole) return false
  return HIERARCHY[userRole] >= HIERARCHY[minRole]
}
