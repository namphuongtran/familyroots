/**
 * The invitations repository: fetch (`../api/invitations-api`) → parse (the zod
 * schema in `../model/invitation-dto`) → map to domain
 * (`@/domain/invitation/invitation`). Same three steps, in the same one place, as
 * `features/persons/server/persons-repository.ts`.
 *
 * It also owns one thing that repository has no reason to: keeping the invitation
 * token out of an error message. `apiFetch` builds
 * `new NetworkError(`request to ${path} failed`)`
 * (`shared/http/api-client.ts:119`) from the path it was given, and for this one
 * route the path carries a bearer credential
 * (`docs/contracts/rest-invitations-api.md:74`). A `NetworkError` is the kind of
 * thing a screen shows, a boundary logs, and Sentry reports, so the token is
 * removed here — at the seam where the token-bearing path stops being needed —
 * rather than trusting every later reader to remember.
 */

import { NetworkError } from '@/shared/http/errors'
import { unwrapData } from '@/shared/http/envelope'
import { redactInvitationToken } from '@/shared/telemetry/redact'
import type { AcceptedInvitation } from '@/domain/invitation/invitation'
import * as api from '../api/invitations-api'
import type { InvitationsApiCallOptions } from '../api/invitations-api'
import { invitationAcceptedDtoSchema, toAcceptedInvitation } from '../model/invitation-dto'

export type { InvitationsApiCallOptions }

/**
 * `POST /invitations/{token}/accept`.
 *
 * Every refusal leaves this function as the `ApiError` the transport built, with
 * its `code` and `status` intact, because deciding what a refusal *means* is
 * `refusalFor`'s job in `@/domain/invitation/invitation` and it must stay testable
 * without a network. The only error this function rewrites is the transport-level
 * `NetworkError`, and only its message.
 */
export async function acceptInvitation(
  token: string,
  options: InvitationsApiCallOptions,
): Promise<AcceptedInvitation> {
  try {
    const body = await api.acceptInvitation(token, options)
    return unwrapData(body, (raw) => toAcceptedInvitation(invitationAcceptedDtoSchema.parse(raw)))
  } catch (error) {
    if (error instanceof NetworkError) {
      // `cause` is dropped deliberately: it is whatever `fetch` threw, and a
      // `TypeError` from an aborted or failed request can carry the request URL in
      // some engines. Nothing above needs the cause — the screen branches on the
      // error's class, not on its innards.
      throw new NetworkError(redactInvitationToken(error.message))
    }
    throw error
  }
}
