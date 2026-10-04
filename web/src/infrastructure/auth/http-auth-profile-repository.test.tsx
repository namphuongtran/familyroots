/**
 * #182: `onboard` returned the whole `{"data": {...}}` body, so every field a caller read
 * off it was `undefined`. Nothing on screen reads the result yet, which is why no user
 * has met it; this file is what notices first.
 *
 * `.tsx` because only the `component` project starts the MSW server (`vitest.setup.ts`),
 * and its jsdom is where this repository runs: axios takes its browser adapter there, as it
 * does in production. #183 deletes this file with the repository; the register half's test,
 * `register/page.success.test.tsx`, is the one that outlives it.
 *
 * The fixture is typed with the OpenAPI schema `POST /auth/onboard` declares
 * (`responses=created(RegisterResponse)`, `backend/app/api/v1/auth.py`), so it cannot drift
 * from the real body without failing `pnpm type-check`.
 */
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { envelope, server } from '@/shared/testing/msw'
import { authProfileRepository } from './http-auth-profile-repository'

vi.mock('@/lib/supabase/client', () => ({
  createClientOrNull: vi.fn(() => null),
}))

const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'

function registerResponseFixture(): components['schemas']['RegisterResponse'] {
  return {
    user_id: '11111111-1111-1111-1111-111111111111',
    email: 'a@example.com',
    full_name: 'Trần Văn A',
    clan_id: CLAN_ID,
    is_approved: false,
    message: 'Đã gửi yêu cầu tham gia',
  }
}

describe('authProfileRepository.onboard', () => {
  it('returns the RegisterResponse, not the envelope around it', async () => {
    server.use(
      http.post('*/api/v1/auth/onboard', () =>
        HttpResponse.json(envelope(registerResponseFixture()), { status: 201 }),
      ),
    )

    const result = await authProfileRepository.onboard({
      clan_action: 'join',
      clan_code: 'nguyen-huu-thanh-oai',
    })

    expect(result.clan_id).toBe(CLAN_ID)
  })
})
