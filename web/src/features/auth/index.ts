/**
 * Public surface of the `auth` slice. ADR-061 § 1.
 *
 * `cross-feature-only-via-index` (`.dependency-cruiser.cjs`) makes this file the only way into
 * the slice for other features, `src/app/**` and the shared layout components. The transport in
 * `api/` is not re-exported, for the reason `features/persons/index.ts` gives: a caller gets the
 * session and the actions, never an unparsed body.
 *
 * What stays outside the slice, per ADR-061 § 1: the `current_clan_id` cookie and the request
 * context (`@/shared/http`), the capability table (`@/domain/capability`), and the access-state
 * function (`@/domain/session/access-state`), which the server guard (#186) calls too.
 */

export type { Membership, Session } from '@/domain/session/session'
export type { AccessState } from '@/domain/session/access-state'

export { landingPath } from './model/landing'
export { useSession } from './hooks/use-session'
export { useAuthActions } from './hooks/use-auth-actions'

export { ClanSuspendedScreen } from './ui/ClanSuspendedScreen'
export { LoginScreen } from './ui/LoginScreen'
export { PendingApprovalScreen } from './ui/PendingApprovalScreen'
export { RegisterScreen } from './ui/RegisterScreen'
export { SelectClanScreen } from './ui/SelectClanScreen'
export { SupabaseSetupNotice } from './ui/SupabaseSetupNotice'
export { VerifyEmailScreen } from './ui/VerifyEmailScreen'
