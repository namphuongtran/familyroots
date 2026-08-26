'use client'

/**
 * The one mutation on the invitee surface: accept the invitation this token names.
 *
 * A mutation and not a query, and this is the whole reason the screen has a button
 * instead of accepting on load. `POST /invitations/{token}/accept`
 * (`docs/contracts/rest-invitations-api.md:64`) grants a clan role and writes an
 * audit event (`:71`) — it is not idempotent in any sense a reader can rely on, and
 * a second call answers `invitation.not_pending`. A GET-shaped page that accepted
 * during render would fire on a link prefetch, on a React strict-mode double
 * render, and on every reload of the address bar. So the render is a `GET` that
 * changes nothing, and the accept happens when a person presses a button.
 *
 * No cache invalidation. The caller is not a member of any clan when this runs, so
 * there is no clan-scoped `persons`/`tree`/`events` cache entry for a new
 * membership to invalidate. What does go stale is `useAuth()`'s membership list —
 * and the success state's only action is a normal navigation to
 * `/{locale}/select-clan`, which resolves memberships from the server on arrival.
 * Wiring a cross-feature invalidation for a screen whose next step is a page load
 * would be a second mechanism for the same effect.
 */

import { useMutation } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import type { AcceptedInvitation } from '@/domain/invitation/invitation'
import { acceptInvitation } from '../server/invitations-repository'

export interface AcceptInvitationOptions {
  /** The opaque token from the invitation link. Never logged — see `@/shared/telemetry/redact`. */
  token: string
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
}

export function useAcceptInvitation(options: AcceptInvitationOptions) {
  const { token, context, refreshAuth } = options

  return useMutation<AcceptedInvitation, unknown, void>({
    mutationFn: () => acceptInvitation(token, { context, refreshAuth }),
  })
}
