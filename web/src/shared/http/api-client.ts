/**
 * The single way the web client talks to the API.
 *
 * Built on standard fetch rather than axios so one implementation serves Server
 * Components, the browser, and tests — and so Next's `next: { tags }` cache
 * controls are available at all.
 *
 * Returns the raw enveloped JSON. Unwrapping is the caller's job
 * (`unwrapData` / `unwrapPage`), which keeps this module free of any knowledge
 * about payload shapes.
 */

import { newTraceparent } from '@/shared/telemetry/trace'
import { ApiError, NetworkError, parseErrorBody } from './errors'
import type { RequestContext } from './request-context'

const DEFAULT_TIMEOUT_MS = 30_000

/**
 * The transport seam. Deliberately narrower than `typeof fetch`: apiFetch always
 * builds the Request itself and never passes a string or a URL, so a test double
 * only has to handle a Request. The global `fetch` still satisfies this, while a
 * double typed to it would not satisfy `typeof fetch` (parameters are
 * contravariant under strictFunctionTypes).
 */
export type FetchLike = (request: Request, init?: RequestInit) => Promise<Response>

function apiBaseUrl(): string {
  const origin = process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'
  return `${origin.replace(/\/+$/, '')}/api/v1`
}

export interface ApiFetchOptions {
  context: RequestContext
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | null | undefined>
  signal?: AbortSignal
  timeoutMs?: number
  next?: { tags?: string[]; revalidate?: number | false }
  /**
   * Called at most once, on a 401. Returns a context with a fresh token, or null
   * when the session is truly gone. Sign-out is the caller's decision, not this
   * module's — a transport layer must not navigate.
   */
  refreshAuth?: () => Promise<RequestContext | null>
  /** Injection seam for tests. */
  fetchImpl?: FetchLike
}

function buildUrl(path: string, query: ApiFetchOptions['query']): string {
  const url = new URL(`${apiBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined) continue
    url.searchParams.set(key, String(value))
  }
  return url.toString()
}

function buildRequest(
  url: string,
  traceparent: string,
  options: ApiFetchOptions,
  context: RequestContext,
): Request {
  const headers = new Headers({
    accept: 'application/json',
    'accept-language': context.locale,
    traceparent,
  })
  if (context.accessToken) headers.set('authorization', `Bearer ${context.accessToken}`)
  if (context.clanId) headers.set('x-current-clan-id', context.clanId)

  const hasBody = options.body !== undefined
  if (hasBody) headers.set('content-type', 'application/json')

  return new Request(url, {
    method: options.method ?? 'GET',
    headers,
    body: hasBody ? JSON.stringify(options.body) : undefined,
  })
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.headers.get('content-length') === '0') return null
  const text = await response.text()
  if (text.length === 0) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function traceIdFromResponse(response: Response): string | null {
  const header = response.headers.get('traceparent')
  if (!header) return null
  const parts = header.split('-')
  return parts.length >= 2 && parts[1].length === 32 ? parts[1] : null
}

export async function apiFetch(path: string, options: ApiFetchOptions): Promise<unknown> {
  const url = buildUrl(path, options.query)
  const traceparent = newTraceparent()

  const send = async (context: RequestContext): Promise<Response> => {
    const timeout = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
    const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
    const request = buildRequest(url, traceparent, options, context)
    const doFetch: FetchLike = options.fetchImpl ?? fetch
    try {
      return await doFetch(request, { signal, next: options.next } as RequestInit)
    } catch (cause) {
      // A caller-initiated abort is a decision, not a failure. Rethrowing it
      // unchanged keeps "the user navigated away" from reaching the UI as "the
      // network is down, retry?". The timeout signal is ours and still becomes a
      // NetworkError, which is what the error taxonomy says it is.
      if (options.signal?.aborted) throw cause
      throw new NetworkError(`request to ${path} failed`, { cause })
    }
  }

  let response = await send(options.context)

  // 401 means the credential itself is bad: refresh exactly once, then retry.
  // 403 means policy denied a valid credential — never refresh, never retry.
  if (response.status === 401 && options.refreshAuth) {
    const refreshed = await options.refreshAuth()
    if (refreshed !== null) {
      response = await send(refreshed)
    }
  }

  const body = await readBody(response)

  if (!response.ok) {
    throw parseErrorBody(body, response.status, traceIdFromResponse(response))
  }
  return body
}

export { ApiError }
