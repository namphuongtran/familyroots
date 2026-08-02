import { describe, expect, it, vi } from 'vitest'
import { apiFetch, type FetchLike } from './api-client'
import { ApiError, NetworkError } from './errors'
import type { RequestContext } from './request-context'

// Every double is `vi.fn<FetchLike>()`. `vi.fn(async () => ...)` would infer an
// empty parameter tuple and make `mock.calls[0][0]` a compile error.
const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('apiFetch headers', () => {
  it('sends the three contract headers plus a traceparent', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: [] }))
    await apiFetch('/persons', { context, fetchImpl })

    const request = fetchImpl.mock.calls[0][0]
    expect(request.headers.get('authorization')).toBe('Bearer tok-1')
    expect(request.headers.get('accept-language')).toBe('vi')
    expect(request.headers.get('x-current-clan-id')).toBe('clan-1')
    expect(request.headers.get('traceparent')).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/)
  })

  it('omits the clan header when no clan is selected', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: [] }))
    await apiFetch('/me/clans', { context: { ...context, clanId: null }, fetchImpl })

    expect(fetchImpl.mock.calls[0][0].headers.has('x-current-clan-id')).toBe(false)
  })

  it('omits Authorization when unauthenticated', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: {} }))
    await apiFetch('/auth/login', {
      context: { ...context, accessToken: null },
      method: 'POST',
      body: { email: 'a@b.c' },
      fetchImpl,
    })

    expect(fetchImpl.mock.calls[0][0].headers.has('authorization')).toBe(false)
  })
})

describe('apiFetch query and body', () => {
  it('serialises query params and drops null and undefined', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse({ data: [] }))
    await apiFetch('/persons', {
      context,
      query: { limit: 20, cursor: null, search: 'Nguyễn', include: undefined },
      fetchImpl,
    })

    const url = new URL(fetchImpl.mock.calls[0][0].url)
    expect(url.searchParams.get('limit')).toBe('20')
    expect(url.searchParams.get('search')).toBe('Nguyễn')
    expect(url.searchParams.has('cursor')).toBe(false)
    expect(url.searchParams.has('include')).toBe(false)
  })

  it('returns null for 204 rather than trying to parse an empty body', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => new Response(null, { status: 204 }))
    await expect(
      apiFetch('/documents/d-1', { context, method: 'DELETE', fetchImpl }),
    ).resolves.toBeNull()
  })
})

describe('apiFetch errors', () => {
  it('throws ApiError carrying the code and the trace id from the response header', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'person_not_found', message: 'Không tìm thấy', detail: {} } },
        {
          status: 404,
          headers: {
            'content-type': 'application/json',
            traceparent: '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01',
          },
        },
      ),
    )

    const error = await apiFetch('/persons/p-1', { context, fetchImpl }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('person_not_found')
    expect((error as ApiError).traceId).toBe('4bf92f3577b34da6a3ce929d0e0e4736')
  })

  it('does not refresh or retry on 403 — policy denial is not a credential problem', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'email_not_verified', message: 'Chưa xác thực' } },
        { status: 403, headers: { 'content-type': 'application/json' } },
      ),
    )
    const refreshAuth = vi.fn(async () => context)

    await expect(apiFetch('/persons', { context, fetchImpl, refreshAuth })).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(refreshAuth).not.toHaveBeenCalled()
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    const fetchImpl = vi
      .fn<FetchLike>()
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: 'invalid_token', message: 'hết hạn' } },
          { status: 401, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ data: [] }))
    const refreshAuth = vi.fn(async () => ({ ...context, accessToken: 'tok-2' }))

    await expect(apiFetch('/persons', { context, fetchImpl, refreshAuth })).resolves.toEqual({
      data: [],
    })
    expect(refreshAuth).toHaveBeenCalledTimes(1)
    expect(fetchImpl.mock.calls[1][0].headers.get('authorization')).toBe('Bearer tok-2')
  })

  it('gives up after one refresh — never loops', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'invalid_token', message: 'hết hạn' } },
        { status: 401, headers: { 'content-type': 'application/json' } },
      ),
    )
    const refreshAuth = vi.fn(async () => ({ ...context, accessToken: 'tok-2' }))

    await expect(apiFetch('/persons', { context, fetchImpl, refreshAuth })).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(refreshAuth).toHaveBeenCalledTimes(1)
  })

  it('throws the original 401 when refresh yields no session', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'invalid_token', message: 'hết hạn' } },
        { status: 401, headers: { 'content-type': 'application/json' } },
      ),
    )
    const refreshAuth = vi.fn(async () => null)

    const error = await apiFetch('/persons', { context, fetchImpl, refreshAuth }).catch(
      (e: unknown) => e,
    )
    expect((error as ApiError).status).toBe(401)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('wraps a transport failure as NetworkError, not ApiError', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => {
      throw new TypeError('Failed to fetch')
    })
    await expect(apiFetch('/persons', { context, fetchImpl })).rejects.toBeInstanceOf(NetworkError)
  })

  it('rethrows a caller abort unchanged instead of calling it a NetworkError', async () => {
    // "The user navigated away" must not reach the UI as "the network is down"
    // with a retry button. Only a genuine transport failure becomes NetworkError.
    const controller = new AbortController()
    controller.abort(new DOMException('navigated away', 'AbortError'))
    const fetchImpl = vi.fn<FetchLike>(async (_request, init) => {
      init?.signal?.throwIfAborted()
      return jsonResponse({ data: [] })
    })

    const error = await apiFetch('/persons', {
      context,
      signal: controller.signal,
      fetchImpl,
    }).catch((e: unknown) => e)

    expect(error).not.toBeInstanceOf(NetworkError)
    expect((error as DOMException).name).toBe('AbortError')
  })
})
