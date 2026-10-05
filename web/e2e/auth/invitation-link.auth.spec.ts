import { expect, test, type APIRequestContext } from '@playwright/test'
import type { components } from '../../src/generated/api-types'
import { authStackInputs, SEEDED_PASSWORD, SEEDED_USERS } from './fixtures'

/**
 * #191, ADR-062. The link the backend hands an admin opens the invitation page.
 *
 * `backend/tests/integration/test_invitation_invite_url.py` pins the string in the 201 body.
 * This file checks where the string goes: the admin creates an invitation through the real
 * backend, and the `invite_url` from that body is opened, unchanged, in a browser with no
 * session. The page answers with its signed-out heading and with the `Referrer-Policy` header
 * `next.config.ts` sets only on `/:locale/invitations/:token`. The two together say the link
 * reached that page and not some other page that also renders. The heading is the Vietnamese
 * one, so it also reads the locale the request named.
 *
 * **Nothing here asserts the link's origin or path.** Those are the backend test's string. A
 * check on them here would fail first under the misconfiguration the second control names, and
 * hide the reading that matters: what a person who opens the link sees. **So the backend has to
 * run with `INVITE_LINK_ORIGIN` set to this harness's web origin** (`web/CLAUDE.md`, "The
 * authenticated e2e harness"). On its `http://localhost:3000` default, the first case fails on a
 * refused connection.
 *
 * **Two controls, each with a reading that differs from the passing one** (`.claude/rules/testing.md`,
 * question 2):
 *
 * - **The old `accept_path`, opened against the same web origin.** `web/src/app/api/` holds only
 *   `auth/callback`, so it answers 404, with no invitation heading and no `Referrer-Policy`.
 * - **The link as a backend with `INVITE_LINK_ORIGIN` set to the API origin would build it**,
 *   the mistake ADR-056 and ADR-057 both warn against. The path is the one the backend composed
 *   and only the origin differs, so this is what that misconfiguration hands an admin. The API
 *   answers it with a 404 and no heading.
 *
 * Run on 2026-10-05 against a real misconfigured backend too, `INVITE_LINK_ORIGIN` set to its own
 * origin: the first case failed on `Expected: 200, Received: 404`, and both controls passed. That
 * link answered the API's JSON 404, `{"error":{"code":"not_found",…}}`, so there was no page to
 * render a heading. The pull request for #191 holds the readings.
 *
 * The admin acts through the backend directly, with a token from GoTrue's password grant, as
 * `make seed`'s admin. The invitation screen that would do this in the browser (spec § 7.10c) is
 * not built. The describe runs in one worker, so a run creates one invitation. It invites a fresh
 * address, because a reused one answers `invitation.pending_exists`, and revokes it afterwards so
 * the seeded clan does not collect pending rows. None of these requests is under `/api/v1/auth` or `/api/v1/invitations`, so
 * none spends the backend's 20-per-minute bucket.
 */

/** `messages/vi.json`, `invitation.sign_in_required_heading`. */
const SIGN_IN_REQUIRED = 'Hãy đăng nhập trước'

/** Typed from the generated contract, so a renamed field fails `pnpm type-check` here too. */
type CreatedInvitation = components['schemas']['InvitationCreatedResponse']
type ClanMembership = components['schemas']['UserClanMembership']

async function adminAccessToken(request: APIRequestContext): Promise<string> {
  const response = await request.post(
    `${authStackInputs().supabaseUrl}/auth/v1/token?grant_type=password`,
    {
      headers: { apikey: authStackInputs().supabaseAnonKey },
      data: { email: SEEDED_USERS.admin.email, password: SEEDED_PASSWORD },
    },
  )
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { access_token: string }
  return body.access_token
}

async function adminClanId(request: APIRequestContext, token: string): Promise<string> {
  const response = await request.get(`${authStackInputs().apiOrigin}/api/v1/me/clans`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { data: ClanMembership[] }
  const clan = body.data.find((row) => row.clan_slug === SEEDED_USERS.admin.clanSlug)
  if (!clan)
    throw new Error(`the seeded admin holds no membership in ${SEEDED_USERS.admin.clanSlug}`)
  return clan.clan_id
}

test.describe('the link POST /clans/{clan_id}/invitations hands an admin', () => {
  // No session: the relative who opens the link has not signed in.
  test.use({ storageState: { cookies: [], origins: [] } })
  // One worker, so `beforeAll` creates one invitation rather than one per worker.
  test.describe.configure({ mode: 'default' })

  let invitation: CreatedInvitation
  let revoke: () => Promise<void>

  test.beforeAll(async ({ playwright }) => {
    const request = await playwright.request.newContext()
    const token = await adminAccessToken(request)
    const clanId = await adminClanId(request, token)
    const headers = {
      Authorization: `Bearer ${token}`,
      'X-Current-Clan-Id': clanId,
      'Accept-Language': 'vi',
    }
    const invitations = `${authStackInputs().apiOrigin}/api/v1/clans/${clanId}/invitations`

    const response = await request.post(invitations, {
      headers,
      data: { email: `invite-link-${crypto.randomUUID()}@familyroots.example.com`, role: 'viewer' },
    })
    expect(response.status(), await response.text()).toBe(201)
    invitation = ((await response.json()) as { data: CreatedInvitation }).data

    revoke = async () => {
      const revoked = await request.delete(`${invitations}/${invitation.id}`, { headers })
      expect(revoked.status(), await revoked.text()).toBe(204)
      await request.dispose()
    }
  })

  test.afterAll(async () => {
    await revoke?.()
  })

  test('invite_url, opened as it is, lands on the invitation page', async ({ page }) => {
    const response = await page.goto(invitation.invite_url)

    expect(response?.status()).toBe(200)
    expect(response?.headers()['referrer-policy']).toBe('no-referrer')
    await expect(page.getByRole('heading', { name: SIGN_IN_REQUIRED })).toBeVisible()
  })

  test('control: the old accept_path, on the same web origin, is a 404 with no invitation', async ({
    page,
  }) => {
    const response = await page.goto(`/api/v1/invitations/${invitation.token}/accept`)

    expect(response?.status()).toBe(404)
    expect(response?.headers()['referrer-policy']).toBeUndefined()
    await expect(page.getByRole('heading', { name: SIGN_IN_REQUIRED })).toHaveCount(0)
  })

  test('control: the link built on the API origin does not render the invitation page', async ({
    page,
  }) => {
    const misbuilt = `${authStackInputs().apiOrigin}${new URL(invitation.invite_url).pathname}`

    const response = await page.goto(misbuilt)

    expect(response?.status()).toBe(404)
    await expect(page.getByRole('heading', { name: SIGN_IN_REQUIRED })).toHaveCount(0)
  })
})
