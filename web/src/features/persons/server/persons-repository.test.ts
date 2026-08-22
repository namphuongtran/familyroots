import { describe, expect, it, vi } from 'vitest'
import type { FetchLike } from '@/shared/http/api-client'
import { ApiError } from '@/shared/http/errors'
import { createSingleFlight } from '@/shared/http/refresh'
import type { RequestContext } from '@/shared/http/request-context'
import {
  batchGetPersons,
  createPerson,
  deletePerson,
  getPerson,
  listPersons,
  restorePerson,
  searchPersons,
  updatePerson,
} from './persons-repository'

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

/** Same fixture shape as `model/person-dto.test.ts` and `api/persons-api.test.ts`. */
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

describe('getPerson — envelope → schema → domain', () => {
  it('returns a domain Person, not a DTO', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: personFixture({ full_name: 'Trần Thị Bình', version: 4 }) }),
    )

    const person = await getPerson('id-1', {}, { context, fetchImpl })

    expect(person.fullName).toBe('Trần Thị Bình')
    expect(person.version).toBe(4)
    expect(person.birthDate).toEqual({
      date: '1750-01-01',
      precision: 'circa',
      display: 'khoảng 1750',
      lunar: '15/08 Nhâm Tý',
    })
    // A DTO carries snake_case; a leaked DTO would still have this key.
    expect(person).not.toHaveProperty('full_name')
  })

  it('rejects a body that skipped the envelope', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => jsonResponse(personFixture()))
    await expect(getPerson('id-1', {}, { context, fetchImpl })).rejects.toThrow()
  })
})

describe('listPersons — Page<Person> and the invalid_cursor rule', () => {
  it('maps the cursor-paginated list into a Page<Person>', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({
        data: [personFixture(), personFixture({ id: '44444444-4444-4444-4444-444444444444' })],
        meta: { cursor: 'opaque-cursor-token', has_more: true, limit: 20 },
      }),
    )

    const page = await listPersons({ limit: 20 }, { context, fetchImpl })

    expect(page.items).toHaveLength(2)
    expect(page.items[1].id).toBe('44444444-4444-4444-4444-444444444444')
    expect(page.cursor).toBe('opaque-cursor-token')
    expect(page.hasMore).toBe(true)
  })

  it('drops the cursor and refetches page one on a 400 invalid_cursor', async () => {
    const fetchImpl = vi.fn<FetchLike>(async (request) => {
      const url = new URL(request.url)
      if (url.searchParams.has('cursor')) {
        return jsonResponse(
          { error: { code: 'invalid_cursor', message: 'Con trỏ không hợp lệ', detail: {} } },
          { status: 400 },
        )
      }
      return jsonResponse({
        data: [personFixture()],
        meta: { cursor: 'fresh-cursor', has_more: true, limit: 20 },
      })
    })

    const page = await listPersons({ cursor: 'stale-token' }, { context, fetchImpl })

    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(page.cursor).toBe('fresh-cursor')
    const secondUrl = new URL(fetchImpl.mock.calls[1][0].url)
    expect(secondUrl.searchParams.has('cursor')).toBe(false)
  })

  it('does not retry, and surfaces the code, for any other error', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'validation_error', message: 'x', detail: {} } },
        { status: 422 },
      ),
    )

    const error = await listPersons({}, { context, fetchImpl }).catch((e: unknown) => e)

    expect(fetchImpl).toHaveBeenCalledTimes(1)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('validation_error')
  })

  /**
   * Negative control for the retry above, run by hand and reverted (not
   * committed as a permanent test — the point is proving the *real* retry
   * branch can fail, not keeping a second copy of it):
   *
   *   1. Change the `error.code === INVALID_CURSOR_CODE` check in
   *      `persons-repository.ts`'s `listPersons` to `false`.
   *   2. `pnpm vitest run persons-repository.test.ts` — "drops the cursor…"
   *      fails: `fetchImpl` was called once, not twice, and the assertion on
   *      `page.cursor` throws because the caught `ApiError` propagated instead.
   *   3. Revert the change.
   */
})

describe('searchPersons — a plain array under data, no meta', () => {
  it('maps every hit into a PersonSearchHit', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({
        data: [
          {
            id: '11111111-1111-1111-1111-111111111111',
            full_name: 'Nguyễn Văn An',
            gender: 'male',
            birth_date: { date: '1750-01-01', precision: 'circa', display: null, lunar: null },
            avatar_url: null,
            version: 1,
            generation: 3,
            membership_role: 'viewer',
            is_founder: false,
          },
        ],
      }),
    )

    const hits = await searchPersons({ q: 'An' }, { context, fetchImpl })

    expect(hits).toHaveLength(1)
    expect(hits[0].fullName).toBe('Nguyễn Văn An')
    expect(hits[0].generation).toBe(3)
  })
})

describe('batchGetPersons — resolved items and unresolved errors, never mixed', () => {
  it('keeps data and meta.errors apart', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({
        data: [personFixture({ id: '55555555-5555-5555-5555-555555555555' })],
        meta: {
          errors: [{ id: '66666666-6666-6666-6666-666666666666', code: 'person_not_found' }],
        },
      }),
    )

    const result = await batchGetPersons(
      {
        ids: ['55555555-5555-5555-5555-555555555555', '66666666-6666-6666-6666-666666666666'],
        profile: 'summary',
      },
      { context, fetchImpl },
    )

    expect(result.items).toHaveLength(1)
    expect(result.items[0].id).toBe('55555555-5555-5555-5555-555555555555')
    expect(result.errors).toEqual([
      { id: '66666666-6666-6666-6666-666666666666', code: 'person_not_found' },
    ])
  })

  it('defaults to no errors when meta.errors is absent', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: [personFixture()], meta: {} }),
    )
    const result = await batchGetPersons(
      { ids: ['11111111-1111-1111-1111-111111111111'], profile: 'summary' },
      { context, fetchImpl },
    )
    expect(result.errors).toEqual([])
  })
})

describe('createPerson / updatePerson — write bodies carry no zod validation', () => {
  it('createPerson maps the created resource', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: personFixture({ full_name: 'Lê Văn Cường' }) }, { status: 201 }),
    )
    const person = await createPerson(
      { full_name: 'Lê Văn Cường', gender: 'male', nationality: 'VN' } as Parameters<
        typeof createPerson
      >[0],
      { context, fetchImpl },
    )
    expect(person.fullName).toBe('Lê Văn Cường')
  })

  /**
   * S-029 recorded this decision (`../api/persons-api.ts`, `web/CLAUDE.md`):
   * a write body is caller-constructed, not untrusted wire data, so nothing
   * here validates it — it goes to `JSON.stringify` unchanged. This proves
   * that decision rather than asserting it in prose: an extra key no
   * generated type declares survives the round trip to the wire, which a
   * zod `.parse()` with no `.passthrough()` would have stripped or rejected.
   */
  it('forwards a body with an unrecognised key untouched — proof nothing validates it at runtime', async () => {
    let sentBody: unknown
    const fetchImpl = vi.fn<FetchLike>(async (request) => {
      sentBody = JSON.parse(await request.clone().text())
      return jsonResponse({ data: personFixture() }, { status: 201 })
    })

    const bodyWithExtraKey = {
      full_name: 'Phạm Thị Dung',
      gender: 'female',
      nationality: 'VN',
      not_a_real_field: 'should still be sent',
    }

    await createPerson(bodyWithExtraKey as unknown as Parameters<typeof createPerson>[0], {
      context,
      fetchImpl,
    })

    expect(sentBody).toMatchObject({ not_a_real_field: 'should still be sent' })
  })

  it('updatePerson maps the updated resource', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: personFixture({ version: 2 }) }),
    )
    // `expected_version` (ADR-017) is the only required field — every content
    // field on PersonUpdateRequest is optional, so this literal needs nothing else.
    const person = await updatePerson('id-1', { expected_version: 1 }, { context, fetchImpl })
    expect(person.version).toBe(2)
  })
})

describe('deletePerson / restorePerson — MessageData → PersonActionResult', () => {
  it('deletePerson maps the message envelope', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: { message: 'Đã xóa', id: 'id-1' } }),
    )
    const result = await deletePerson('id-1', { context, fetchImpl })
    expect(result).toEqual({ message: 'Đã xóa', id: 'id-1' })
  })

  it('restorePerson maps the message envelope', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse({ data: { message: 'Đã khôi phục', id: 'id-1' } }),
    )
    const result = await restorePerson('id-1', { context, fetchImpl })
    expect(result).toEqual({ message: 'Đã khôi phục', id: 'id-1' })
  })
})

describe('the spine error paths — 401 refreshes once and shares the refresh; 403 never refreshes', () => {
  it('a 401 triggers exactly one refresh, shared by two concurrent repository calls', async () => {
    let resolveRefresh: (ctx: RequestContext) => void = () => {}
    const refreshOperation = vi.fn(
      () =>
        new Promise<RequestContext>((resolve) => {
          resolveRefresh = resolve
        }),
    )
    const refreshAuth = createSingleFlight(refreshOperation)

    const fetchImpl = vi.fn<FetchLike>(async (request) => {
      if (request.headers.get('authorization') === 'Bearer fresh-token') {
        return jsonResponse({ data: personFixture() })
      }
      return jsonResponse(
        { error: { code: 'token_expired', message: 'Token expired', detail: {} } },
        { status: 401 },
      )
    })

    const callA = getPerson('a', {}, { context, refreshAuth, fetchImpl })
    const callB = getPerson('b', {}, { context, refreshAuth, fetchImpl })

    // Flush every pending microtask so both calls reach their (still-pending)
    // `await refreshAuth()` before either is resolved — the same technique
    // `refresh.test.ts` uses to prove `createSingleFlight` itself.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(refreshOperation).toHaveBeenCalledTimes(1)

    resolveRefresh({ ...context, accessToken: 'fresh-token' })

    const [personA, personB] = await Promise.all([callA, callB])
    expect(personA.fullName).toBe('Nguyễn Văn An')
    expect(personB.fullName).toBe('Nguyễn Văn An')
    expect(refreshOperation).toHaveBeenCalledTimes(1)
  })

  /**
   * Negative control, run by hand and reverted: wrap `refreshOperation`
   * above in a *second, independent* `createSingleFlight` per call (i.e.
   * pass `createSingleFlight(refreshOperation)` fresh to each of `callA`
   * and `callB`) instead of sharing one `refreshAuth`. `refreshOperation` is
   * then called twice and the final `toHaveBeenCalledTimes(1)` fails —
   * proving the test is actually pinned on *sharing* the in-flight refresh,
   * not merely on a 401 being handled at all.
   */

  it('a 403 never calls refreshAuth — policy denial is not a stale credential', async () => {
    const refreshAuth = vi.fn(async (): Promise<RequestContext | null> => ({
      ...context,
      accessToken: 'fresh-token',
    }))
    const fetchImpl = vi.fn<FetchLike>(async () =>
      jsonResponse(
        { error: { code: 'clan_suspended', message: 'Chi hội đã bị khóa', detail: {} } },
        { status: 403 },
      ),
    )

    const error = await getPerson('a', {}, { context, refreshAuth, fetchImpl }).catch(
      (e: unknown) => e,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('clan_suspended')
    expect(refreshAuth).not.toHaveBeenCalled()
  })
})
