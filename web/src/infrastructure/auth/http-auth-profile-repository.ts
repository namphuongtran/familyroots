import type {
  AuthenticatedOnboardingInput,
  AuthProfileRepository,
  RegisterInput,
  RegisterResult,
} from '@/application/auth/ports/auth-repository'
import api from '@/lib/api/axios'
import type {
  ApiResponse,
  ClanSwitchResponse,
  UserClanMembership,
  UserClansResponse,
  UserProfile,
} from '@/lib/types'

type UpdateMeInput = {
  full_name?: string
  preferred_locale?: 'vi' | 'en' | 'zh' | 'fr'
}

export class HttpAuthProfileRepository implements AuthProfileRepository {
  async getMe(): Promise<UserProfile> {
    const { data } = await api.get<ApiResponse<UserProfile>>('/auth/me')
    return data.data
  }

  async updateMe(input: UpdateMeInput): Promise<void> {
    await api.patch('/auth/me', input)
  }

  /**
   * **`GET /me/clans` answers `{"data": [...]}`, and this used to read the body as if it
   * answered `{"clans": [...]}`.** Found 2026-08-26 by seed S-070, the first time anything
   * logged in and asked for a real authenticated screen. Read at source: the route returns
   * `{"data": result}` (`backend/app/api/v1/me.py:25`), the committed OpenAPI types call
   * that shape `Envelope_list_UserClanMembership__` with a single `data` member
   * (`src/generated/api-types.ts:2192-2196`, referenced by the 200 response at `:5503`),
   * and `docs/contracts/frontend-integration-guide.md:77` writes it out longhand.
   *
   * The cost was not a visible error. `memberships.clans` came back `undefined`,
   * `hydrateAuthContext`'s `new Set(memberships.map(...))` threw, its own `catch` swallowed
   * that into the identity-only fallback, and the user landed on a clan picker listing
   * nothing — with no console error and no failing test anywhere. Measured against the
   * local stack the same day: `curl` returned
   * `{"data":[{"clan_id":"aaaaaaaa-…","role":"admin", …}]}` HTTP 200.
   *
   * The unwrap is here, in the transport adapter, and not in the caller: the port's shape
   * (`AuthProfileRepository.listMyClans`) stays `{ clans }`, so nothing above this line
   * sees an envelope, which is `web/CLAUDE.md`'s standing rule. The three port doubles in
   * `tests/behavior/auth-and-invalidation.test.ts` are unaffected for the same reason.
   */
  async listMyClans(): Promise<UserClansResponse> {
    const { data } = await api.get<ApiResponse<UserClanMembership[]>>('/me/clans')
    return { clans: data.data }
  }

  /**
   * The same envelope defect as `listMyClans` above, and this one had teeth. Found
   * 2026-08-26 by S-070, from a browser, as an **infinite redirect loop**.
   *
   * `POST /me/clans/{clan_id}/select` answers `{"data": {...}}`
   * (`backend/app/api/v1/me.py:36`). Reading the body as the payload made
   * `selectActiveClan`'s `result.clan_id` `undefined`, so `useAuth.selectClan` called
   * `writeClanCookie(undefined)` and the cookie became the literal string `undefined`.
   * `parseClanCookie` rejects that (it is not a uuid, `src/shared/http/request-context.ts`),
   * so `middleware.ts` bounced the clan-scoped route straight back to `/vi/select-clan`,
   * whose single-clan effect auto-selected again. Measured that day: the round trip
   * repeated until the backend's 20-per-60-second limiter on `/api/v1/auth/*`
   * (`backend/app/main.py:221-226`) answered `429`, because each turn of the loop also
   * re-ran `hydrateAuthContext`.
   *
   * **Nothing was watching.** No unit, component or e2e case navigated a real session, so
   * a loop that a user would have met on their first login sat in `main`.
   */
  async selectClan(clanId: string): Promise<ClanSwitchResponse> {
    const { data } = await api.post<ApiResponse<ClanSwitchResponse>>(`/me/clans/${clanId}/select`)
    return data.data
  }

  async register(input: RegisterInput): Promise<RegisterResult> {
    const { data } = await api.post<RegisterResult>('/auth/register', input)
    return data
  }

  async onboard(input: AuthenticatedOnboardingInput): Promise<RegisterResult> {
    const { data } = await api.post<RegisterResult>('/auth/onboard', input)
    return data
  }
}

export const authProfileRepository = new HttpAuthProfileRepository()
