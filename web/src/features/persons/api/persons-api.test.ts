import { describe, expect, it, vi } from 'vitest'
import type { FetchLike } from '@/shared/http/api-client'
import { ApiError } from '@/shared/http/errors'
import { unwrapData, unwrapPage } from '@/shared/http/envelope'
import type { RequestContext } from '@/shared/http/request-context'
import { personResponseDtoSchema, toPerson } from '../model/person-dto'
import { getPerson, listPersons, searchPersons } from './persons-api'

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

/** Same fixture shape as `model/person-dto.test.ts`; kept minimal here on purpose. */
function personFixture(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    created_by_clan_id: null,
    full_name: 'Nguyễn Văn An',
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: {
      date: '1750-01-01',
      precision: 'circa',
      display: 'khoảng 1750',
      lunar: '15/08 Nhâm Tý',
    },
    death_date: { date: null, precision: 'unknown', display: null, lunar: null },
    birth_place: null,
    death_place: null,
    burial_place: null,
    tomb_location: null,
    residence_place: null,
    religion: null,
    nationality: 'VN',
    occupation: null,
    education_level: null,
    title_rank: null,
    phone: null,
    email: null,
    biography: null,
    avatar_url: null,
    notes: null,
    is_deleted: false,
    created_by: '33333333-3333-3333-3333-333333333333',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

describe('getPerson — the {"data": ...} envelope', () => {
  it('parses a single-resource response through unwrapData, the DTO schema, and the mapper', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: personFixture({ full_name: 'Trần Thị Bình' }) }),
    )

    const body = await getPerson('11111111-1111-1111-1111-111111111111', {}, { context, fetchImpl })
    const person = unwrapData(body, (raw) => toPerson(personResponseDtoSchema.parse(raw)))

    expect(person.id).toBe('11111111-1111-1111-1111-111111111111')
    expect(person.fullName).toBe('Trần Thị Bình')
    expect(person.birthDate).toEqual({
      date: '1750-01-01',
      precision: 'circa',
      display: 'khoảng 1750',
      lunar: '15/08 Nhâm Tý',
    })

    const request = fetchImpl.mock.calls[0][0]
    expect(request.method).toBe('GET')
    expect(new URL(request.url).pathname).toBe(
      '/api/v1/persons/11111111-1111-1111-1111-111111111111',
    )
  })

  it('rejects a body that skipped the envelope, same as the legacy client would have produced', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse(personFixture()))
    const body = await getPerson('p-1', {}, { context, fetchImpl })
    expect(() => unwrapData(body, (raw) => personResponseDtoSchema.parse(raw))).toThrow()
  })
})

describe('listPersons — Page<T>', () => {
  it('parses the cursor-paginated list through unwrapPage into a Page<Person>', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({
        data: [personFixture(), personFixture({ id: '44444444-4444-4444-4444-444444444444' })],
        meta: { cursor: 'opaque-cursor-token', has_more: true, limit: 20 },
      }),
    )

    const body = await listPersons({ limit: 20 }, { context, fetchImpl })
    const page = unwrapPage(body, (raw) => toPerson(personResponseDtoSchema.parse(raw)))

    expect(page.items).toHaveLength(2)
    expect(page.items[1].id).toBe('44444444-4444-4444-4444-444444444444')
    expect(page.cursor).toBe('opaque-cursor-token')
    expect(page.hasMore).toBe(true)
    expect(page.limit).toBe(20)

    const url = new URL(fetchImpl.mock.calls[0][0].url)
    expect(url.searchParams.get('limit')).toBe('20')
  })

  it('carries no total — meta is the cursor triplet only, per the frozen contract', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: [personFixture()], meta: { cursor: null, has_more: false, limit: 20 } }),
    )
    const body = await listPersons({}, { context, fetchImpl })
    const page = unwrapPage(body, (raw) => toPerson(personResponseDtoSchema.parse(raw)))
    expect(page).not.toHaveProperty('total')
    expect(page.hasMore).toBe(false)
    expect(page.cursor).toBeNull()
  })

  it('surfaces a 400 invalid_cursor as an ApiError carrying that code, rather than throwing something opaque', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        {
          error: {
            code: 'invalid_cursor',
            message: 'Con trỏ trang không hợp lệ',
            detail: {},
          },
        },
        { status: 400, headers: { 'content-type': 'application/json' } },
      ),
    )

    const error = await listPersons({ cursor: 'tampered' }, { context, fetchImpl }).catch(
      (e: unknown) => e,
    )
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('invalid_cursor')
    expect((error as ApiError).status).toBe(400)
    // The rule this proves: never repair the cursor from this error. The
    // repository drops it and refetches page one; this layer's job
    // is only to make sure the code survives the round trip un-mangled.
  })
})

describe('searchPersons — a plain array under data, no meta', () => {
  it('parses the array through unwrapData', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({
        data: [
          {
            id: '11111111-1111-1111-1111-111111111111',
            full_name: 'Nguyễn Văn An',
            gender: 'male',
            birth_date: {
              date: '1750-01-01',
              precision: 'circa',
              display: 'khoảng 1750',
              lunar: null,
            },
            avatar_url: null,
            version: 1,
            generation: 3,
            membership_role: 'viewer',
            is_founder: false,
          },
        ],
      }),
    )

    const body = await searchPersons({ q: 'An' }, { context, fetchImpl })
    const hits = unwrapData(body, (raw) => raw)
    expect(Array.isArray(hits)).toBe(true)
    expect((hits as unknown[]).length).toBe(1)

    const url = new URL(fetchImpl.mock.calls[0][0].url)
    expect(url.searchParams.get('q')).toBe('An')
  })
})
