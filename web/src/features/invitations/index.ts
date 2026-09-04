/**
 * Public surface of the `invitations` slice.
 *
 * `cross-feature-only-via-index` (`.dependency-cruiser.cjs`) requires every other
 * feature — and `src/app/**`, which composes the screen — to import through this
 * file rather than reaching into `model/`, `api/`, `server/`, `hooks/`, or `ui/`.
 *
 * `api/invitations-api.ts` is deliberately not re-exported. It returns raw
 * `Promise<unknown>` transport; the parsed repository function is what a caller
 * should get, exactly as `features/persons/index.ts` decided for the same reason.
 * `app-does-not-call-transport` would fail the build for a route file that reached
 * for it anyway.
 */

export type { AcceptedInvitation, InvitationRefusal } from '@/domain/invitation/invitation'
export { asClanRole, refusalFor } from '@/domain/invitation/invitation'

export type { InvitationAcceptedDto } from './model/invitation-dto'
export { invitationAcceptedDtoSchema, toAcceptedInvitation } from './model/invitation-dto'

export type { InvitationsApiCallOptions } from './server/invitations-repository'
export { acceptInvitation } from './server/invitations-repository'

export type { AcceptInvitationOptions } from './hooks/use-accept-invitation'
export { useAcceptInvitation } from './hooks/use-accept-invitation'

export { InvitationAcceptScreen } from './ui/InvitationAcceptScreen'
export type { InvitationAcceptScreenProps } from './ui/InvitationAcceptScreen'
export { useInvitationRequestContext } from './ui/use-invitation-request-context'
export type { InvitationRequestContext } from './ui/use-invitation-request-context'
