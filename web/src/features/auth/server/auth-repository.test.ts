import { describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import type { FetchLike } from '@/shared/http/api-client'
import { ApiError, MalformedResponseError } from '@/shared/http/errors'
import type { RequestContext } from '@/shared/http/request-context'
import { fetchSession, onboard, register, resendVerification, selectClan } from './auth-repository'

/**
 * The fetch → parse → map step for the auth routes, with `fetchImpl` mocked the way
 * `persons-repository.test.ts` does it. Every reading is a mapped domain value, never a DTO
 * field. Fixtures are typed by the generated schemas, so a contract change fails
 * `pnpm type-check` here before it fails a test.
 */

const context: RequestContext = { locale: 'vi', clanId: null, accessToken: 'tok-1' }
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function profileFixture(
  overrides: Partial<components['schemas']['UserProfile']> = {},
): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: CLAN_A,
    clan_name: 'Nguyễn Phúc',
    role: 'admin',
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
    ...overrides,
  }
}

function membershipFixture(): components['schemas']['UserClanMembership'] {
  return {
    clan_id: CLAN_A,
    clan_name: 'Nguyễn Phúc',
    clan_slug: 'nguyen-phuc',
    role: 'admin',
    joined_at: '2026-08-01T00:00:00Z',
  }
}

/** Answers by path, and records each request it saw. */
function routes(answers: Record<string, () => Response>) {
  const seen: Request[] = []
  const fetchImpl = vi.fn<FetchLike>(async (request) => {
    seen.push(request)
    const key = `${request.method} ${new URL(request.url).pathname.replace('/api/v1', '')}`
    const answer = answers[key]
    if (!answer) throw new Error(`no answer for ${key}`)
    return answer()
  })
  return { fetchImpl, seen }
}

describe('fetchSession', () => {
  it('maps GET /auth/me and GET /me/clans into one Session', async () => {
    const { fetchImpl, seen } = routes({
      'GET /auth/me': () =>
        jsonResponse({ data: profileFixture({ platform_role: 'super_admin' }) }),
      'GET /me/clans': () => jsonResponse({ data: [membershipFixture()] }),
    })

    const session = await fetchSession({ context, fetchImpl })

    expect(session).toEqual({
      profile: {
        userId: '11111111-1111-4111-8111-111111111111',
        email: 'lan@example.com',
        fullName: 'Nguyễn Thị Lan',
        preferredLocale: 'vi',
        platformRole: 'super_admin',
        hasPendingMembership: false,
      },
      memberships: [
        { clanId: CLAN_A, clanName: 'Nguyễn Phúc', clanSlug: 'nguyen-phuc', role: 'admin' },
      ],
    })
    expect(seen.map((request) => request.headers.get('authorization'))).toEqual([
      'Bearer tok-1',
      'Bearer tok-1',
    ])
  })

  it('reads has_pending_membership, which is what tells pending from onboarding', async () => {
    const { fetchImpl } = routes({
      'GET /auth/me': () =>
        jsonResponse({
          data: profileFixture({
            clan_id: null,
            clan_name: null,
            role: null,
            is_approved: false,
            has_pending_membership: true,
          }),
        }),
      'GET /me/clans': () => jsonResponse({ data: [] }),
    })

    const session = await fetchSession({ context, fetchImpl })

    expect(session.profile.hasPendingMembership).toBe(true)
    expect(session.memberships).toEqual([])
  })

  it('refuses the pre-envelope {"clans": [...]} body rather than reading no memberships', async () => {
    const { fetchImpl } = routes({
      'GET /auth/me': () => jsonResponse({ data: profileFixture() }),
      'GET /me/clans': () => jsonResponse({ clans: [membershipFixture()] }),
    })

    await expect(fetchSession({ context, fetchImpl })).rejects.toBeInstanceOf(
      MalformedResponseError,
    )
  })

  it('surfaces a 401 from /auth/me as the ApiError the transport built', async () => {
    const { fetchImpl } = routes({
      'GET /auth/me': () =>
        jsonResponse(
          { error: { code: 'invalid_token', message: 'Phiên đã hết hạn', detail: {} } },
          { status: 401 },
        ),
      'GET /me/clans': () => jsonResponse({ data: [] }),
    })

    const failure = await fetchSession({ context, fetchImpl }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).code).toBe('invalid_token')
  })
})

describe('selectClan', () => {
  it('returns the clan id the backend confirmed, read out of the envelope', async () => {
    const { fetchImpl, seen } = routes({
      [`POST /me/clans/${CLAN_A}/select`]: () =>
        jsonResponse({
          data: {
            clan_id: CLAN_A,
            clan_name: 'Nguyễn Phúc',
            clan_slug: 'nguyen-phuc',
            role: 'admin',
            message: 'ok',
          } satisfies components['schemas']['ClanSwitchResponse'],
        }),
    })

    await expect(selectClan(CLAN_A, { context, fetchImpl })).resolves.toBe(CLAN_A)
    expect(seen[0].method).toBe('POST')
  })
})

describe('register', () => {
  it('returns the message the 201 carries, and sends the body untouched', async () => {
    const { fetchImpl, seen } = routes({
      'POST /auth/register': () =>
        jsonResponse(
          {
            data: {
              message: 'Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp theo',
            } satisfies components['schemas']['MessageData'],
          },
          { status: 201 },
        ),
    })
    const body = {
      email: 'lan@example.com',
      password: 'correct horse battery',
      full_name: 'Nguyễn Thị Lan',
      clan_action: 'join' as const,
      clan_code: 'nguyen-phuc',
    }

    const result = await register(body, { context, fetchImpl })

    expect(result).toEqual({
      message: 'Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp theo',
    })
    expect(await seen[0].json()).toEqual(body)
  })

  it('surfaces a 409 clan_slug_taken with its code and the localised message', async () => {
    const { fetchImpl } = routes({
      'POST /auth/register': () =>
        jsonResponse(
          {
            error: {
              code: 'auth.clan_slug_taken',
              message: 'Đường dẫn dòng họ đã được sử dụng',
              detail: {},
            },
          },
          { status: 409 },
        ),
    })

    const failure = await register(
      {
        email: 'lan@example.com',
        password: 'correct horse battery',
        full_name: 'Nguyễn Thị Lan',
        clan_action: 'create',
        clan_name: 'Trần Gia',
        clan_slug: 'tran-gia',
      },
      { context, fetchImpl },
    ).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({
      code: 'auth.clan_slug_taken',
      message: 'Đường dẫn dòng họ đã được sử dụng',
    })
  })
})

describe('onboard', () => {
  it('returns the clan id and approval out of RegisterResponse, not the envelope', async () => {
    const { fetchImpl } = routes({
      'POST /auth/onboard': () =>
        jsonResponse(
          {
            data: {
              user_id: '11111111-1111-4111-8111-111111111111',
              email: 'lan@example.com',
              full_name: 'Nguyễn Thị Lan',
              clan_id: CLAN_A,
              is_approved: false,
              message: 'Đã gửi yêu cầu tham gia',
            } satisfies components['schemas']['RegisterResponse'],
          },
          { status: 201 },
        ),
    })

    const result = await onboard(
      { clan_action: 'join', clan_code: 'nguyen-phuc' },
      { context, fetchImpl },
    )

    expect(result).toEqual({ clanId: CLAN_A, isApproved: false })
  })
})

describe('resendVerification', () => {
  it('posts the email and accepts the message envelope', async () => {
    const { fetchImpl, seen } = routes({
      'POST /auth/resend-verification': () =>
        jsonResponse({ data: { message: 'Đã gửi lại thư xác thực.' } }),
    })

    await resendVerification('lan@example.com', { context, fetchImpl })

    expect(await seen[0].json()).toEqual({ email: 'lan@example.com' })
  })

  it('refuses a 200 that is not the message envelope', async () => {
    const { fetchImpl } = routes({
      'POST /auth/resend-verification': () => jsonResponse({ data: {} }),
    })

    await expect(
      resendVerification('lan@example.com', { context, fetchImpl }),
    ).rejects.toBeInstanceOf(Error)
  })
})
