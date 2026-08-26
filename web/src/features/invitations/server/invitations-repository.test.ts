import { describe, expect, it, vi } from 'vitest'
import type { FetchLike } from '@/shared/http/api-client'
import { ApiError, MalformedResponseError, NetworkError } from '@/shared/http/errors'
import type { RequestContext } from '@/shared/http/request-context'
import { acceptInvitation } from './invitations-repository'

/**
 * A real-shaped token: `secrets.token_urlsafe(32)`
 * (`docs/contracts/rest-invitations-api.md:41`) is 43 URL-safe base64 characters
 * and can contain `-` and `_`.
 */
const TOKEN = 'Zx-9Qa_bC3dEfGhIjKlMnOpQrStUvWxYz0123456789'

/**
 * `clanId: null` on purpose. The invitee surface "takes no `X-Current-Clan-Id`, and
 * cannot" (`docs/contracts/rest-invitations-api.md:72-74`), and
 * `ui/use-invitation-request-context.ts` is what guarantees that in the browser.
 */
const context: RequestContext = { locale: 'vi', clanId: null, accessToken: 'tok-1' }

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function errorResponse(code: string, status: number): Response {
  return jsonResponse(
    { error: { code, message: 'localised by the backend', detail: {} } },
    {
      status,
    },
  )
}

const acceptedBody = {
  data: {
    clan_id: '6f1c4f7e-0000-4000-8000-000000000001',
    role: 'viewer',
    message: 'Đã tham gia dòng họ',
  },
}

describe('acceptInvitation — POST → envelope → schema → domain', () => {
  it('returns the granted membership as a domain value', async () => {
    const fetchImpl = vi.fn<FetchLike>().mockResolvedValue(jsonResponse(acceptedBody))

    const accepted = await acceptInvitation(TOKEN, { context, fetchImpl })

    expect(accepted).toEqual({ clanId: '6f1c4f7e-0000-4000-8000-000000000001', role: 'viewer' })
  })

  it('sends a POST to the contract path, with the token escaped', async () => {
    const fetchImpl = vi.fn<FetchLike>().mockResolvedValue(jsonResponse(acceptedBody))

    await acceptInvitation(TOKEN, { context, fetchImpl })

    const request = fetchImpl.mock.calls[0][0]
    expect(request.method).toBe('POST')
    expect(new URL(request.url).pathname).toBe(`/api/v1/invitations/${TOKEN}/accept`)
  })

  /**
   * Not a stylistic check. `docs/contracts/rest-invitations-api.md:72-74`: the
   * invitee is not a member of the clan yet, so there is no clan for them to
   * select, and sending the header has no effect on this route.
   */
  it('sends no X-Current-Clan-Id, because the invitee has no clan', async () => {
    const fetchImpl = vi.fn<FetchLike>().mockResolvedValue(jsonResponse(acceptedBody))

    await acceptInvitation(TOKEN, { context, fetchImpl })

    expect(fetchImpl.mock.calls[0][0].headers.get('x-current-clan-id')).toBeNull()
  })

  it('leaves an ApiError alone, code and status intact, for the domain to interpret', async () => {
    const fetchImpl = vi
      .fn<FetchLike>()
      .mockResolvedValue(errorResponse('invitation.email_mismatch', 403))

    const error = await acceptInvitation(TOKEN, { context, fetchImpl }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('invitation.email_mismatch')
    expect((error as ApiError).status).toBe(403)
  })

  it('rejects a 200 that is not the contract envelope', async () => {
    const fetchImpl = vi
      .fn<FetchLike>()
      .mockResolvedValue(jsonResponse({ clan_id: 'x', role: 'viewer', message: 'y' }))

    await expect(acceptInvitation(TOKEN, { context, fetchImpl })).rejects.toBeInstanceOf(
      MalformedResponseError,
    )
  })

  /**
   * **The token must not survive in an error message.**
   *
   * `apiFetch` builds `new NetworkError(`request to ${path} failed`)`
   * (`shared/http/api-client.ts:119`) out of the path it was handed, and for this
   * one route the path carries a bearer credential
   * (`docs/contracts/rest-invitations-api.md:74`). A `NetworkError` is exactly the
   * kind of value a boundary logs and Sentry reports, so the repository strips it.
   *
   * The first assertion is the one that matters: the token literal is not in the
   * message. The second pins that the message is still readable, so the fix is not
   * "throw the message away".
   */
  it('strips the token out of the NetworkError a failed transport produces', async () => {
    const fetchImpl = vi.fn<FetchLike>().mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await acceptInvitation(TOKEN, { context, fetchImpl }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(NetworkError)
    expect((error as NetworkError).message).not.toContain(TOKEN)
    expect((error as NetworkError).message).toBe('request to /invitations/[redacted]/accept failed')
  })

  it('the unredacted message really did carry the token, so the case above is not vacuous', async () => {
    // Reads the transport's own behaviour directly: without the repository's
    // redaction there is a token in the message. If this ever stops being true,
    // the redaction has become dead code and the test above proves nothing.
    const { apiFetch } = await import('@/shared/http/api-client')
    const fetchImpl = vi.fn<FetchLike>().mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await apiFetch(`/invitations/${TOKEN}/accept`, {
      context,
      method: 'POST',
      fetchImpl,
    }).catch((e: unknown) => e)

    expect((error as NetworkError).message).toContain(TOKEN)
  })
})
