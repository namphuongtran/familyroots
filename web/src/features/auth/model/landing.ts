import type { AccessState } from '@/domain/session/access-state'

/**
 * Where each access state lands, without the locale prefix. One table, so sign-in, onboarding,
 * the blocked-state screens and the `(dashboard)` layout's interim redirect cannot each send the
 * same state somewhere different.
 *
 * `platform` lands on `/platform/clans`: `platform/` has no index page, and the clans list is the
 * entry the dashboard sidebar links a super_admin to.
 */
const LANDING: Record<AccessState['kind'], string> = {
  'signed-out': '/login',
  'pending-approval': '/pending-approval',
  'needs-onboarding': '/register?mode=oauth',
  'needs-clan-selection': '/select-clan',
  platform: '/platform/clans',
  ready: '/dashboard',
}

export function landingPath(access: AccessState, locale: string): string {
  return `/${locale}${LANDING[access.kind]}`
}
