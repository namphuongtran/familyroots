import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { apiFetch } from '@/shared/http/api-client'
import { unwrapPage } from '@/shared/http/envelope'
import { ApiError } from '@/shared/http/errors'
import type { RequestContext } from '@/shared/http/request-context'
import { errorEnvelope, pageEnvelope, server } from './msw'

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

const asString = (raw: unknown): string => {
  if (typeof raw !== 'string') throw new Error('expected string')
  return raw
}

describe('MSW harness', () => {
  it('serves a contract-shaped page that apiFetch and unwrapPage read together', async () => {
    server.use(
      http.get(`${API}/persons`, () =>
        HttpResponse.json(pageEnvelope(['a', 'b'], { cursor: 'next', has_more: true })),
      ),
    )

    const page = unwrapPage(await apiFetch('/persons', { context }), asString)

    expect(page.items).toEqual(['a', 'b'])
    expect(page.cursor).toBe('next')
    expect(page.hasMore).toBe(true)
  })

  it('serves a contract-shaped error that surfaces as ApiError', async () => {
    server.use(
      http.get(`${API}/persons/p-1`, () =>
        HttpResponse.json(errorEnvelope('person_not_found', 'Không tìm thấy'), { status: 404 }),
      ),
    )

    const error = await apiFetch('/persons/p-1', { context }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('person_not_found')
  })

  it('passes the three contract headers through to the handler', async () => {
    let seen: Headers | null = null
    server.use(
      http.get(`${API}/persons`, ({ request }) => {
        seen = request.headers
        return HttpResponse.json(pageEnvelope<string>([]))
      }),
    )

    await apiFetch('/persons', { context })

    expect(seen!.get('authorization')).toBe('Bearer tok-1')
    expect(seen!.get('accept-language')).toBe('vi')
    expect(seen!.get('x-current-clan-id')).toBe('clan-1')
  })
})
