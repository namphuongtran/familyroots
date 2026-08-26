/**
 * Transport for the invitee surface of the invitations API
 * (`docs/contracts/rest-invitations-api.md:60-78`). Calls `apiFetch` and nothing
 * else — no React, no parsing, no mapping, same discipline as
 * `features/persons/api/persons-api.ts`. Validating the body against
 * `../model/invitation-dto.ts` is `../server/invitations-repository.ts`'s job.
 *
 * One function, because the invitee surface is one route.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'

/**
 * Same shape as `PersonsApiCallOptions`: the `RequestContext` is passed in by the
 * caller rather than read from a global, so the identical function can run in a
 * Server Component and in the browser.
 */
export type InvitationsApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

/**
 * `POST /invitations/{token}/accept` — the path
 * `backend/app/application/invitation/handlers.py:65` returns to the admin as
 * `accept_path`, and the reason seed S-084 exists: it answers `POST` only
 * (`docs/contracts/rest-invitations-api.md:64`), so a relative who pastes it into
 * a browser sends a `GET` and gets an error instead of an invitation.
 *
 * No `X-Current-Clan-Id`, and that is not an omission this file makes: the invitee
 * is not a member of any clan yet, so there is no clan to select, and the header
 * has no effect on this route (`docs/contracts/rest-invitations-api.md:72-74`).
 * `apiFetch` sends the header only when `context.clanId` is set, and
 * `ui/use-invitation-request-context.ts` deliberately sets it to `null`.
 *
 * `encodeURIComponent` on the token: it is `secrets.token_urlsafe(32)`
 * (`docs/contracts/rest-invitations-api.md:41`), so in practice it needs no
 * escaping — but this value arrives from a URL a stranger typed, and building a
 * request path by concatenating unescaped user input is how a path-traversal or an
 * injected query string gets in.
 */
export function acceptInvitation(
  token: string,
  options: InvitationsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/invitations/${encodeURIComponent(token)}/accept`, {
    ...options,
    method: 'POST',
  })
}
