import { requireServerRole, hasMinServerRole } from '@/lib/server/auth-context'

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
  await requireServerRole(requiredRoles, locale)
}

/**
 * Returns true if the given role meets the minimum required role level.
 * Role hierarchy (ascending privilege): viewer < editor < admin < super_admin
 */
export function hasMinRole(userRole: AppRole | undefined, minRole: AppRole): boolean {
  if (!userRole) return false
  if (userRole === 'super_admin') return true
  if (minRole === 'super_admin') return false
  return hasMinServerRole(userRole, minRole)
}
