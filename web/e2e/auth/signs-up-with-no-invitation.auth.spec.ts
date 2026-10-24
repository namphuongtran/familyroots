import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import type { components } from '../../src/generated/api-types'
import { authStackInputs } from './fixtures'
import { mailedConfirmation, onOrigin } from './mail'

/**
 * #291, ADR-075. A person with no invitation and no clan code signs up, confirms the address,
 * signs in, creates a clan on the onboarding form, and lands on the dashboard. Before #291 the
 * register form opened on **join** with its code field required, and production held no clan
 * (`clans 0`, read 2026-10-18), so this person stopped at "Không tìm thấy dòng họ với mã này"
 * whatever they typed.
 *
 * **One test, in steps, because the steps share one person**, as in
 * `invitee-registers.auth.spec.ts`, whose confirmation step this one copies: the local stack
 * mails the link to Mailpit, and a second browser context presses **Xác nhận email**.
 *
 * **What it reads.** The register request's body, which must name no clan. The onboarding
 * form's first state, which must be create. The page the onboarding submit lands on, which must
 * be `/vi/dashboard`. And `GET /me/clans` as the new person: one approved `admin` membership in
 * the clan the form created, under the code the form derived from the name. A clan creator is
 * approved at once (`_assign_clan_membership`, `role="admin"`, `is_approved=True`).
 *
 * **Negative controls, 2026-10-24**, each read against the local stack. With `RegisterScreen.tsx`
 * put back to `origin/main`, the walk failed at its first reading, two radios offered on sign-up
 * where it requires none. With that step's three readings also taken out, it failed on the
 * outcome: the required code field kept the submit in the browser, and the success screen never
 * came. A probe on the same old form, with a code no clan holds, read "Không tìm thấy dòng họ với
 * mã này", the stop the issue names. With onboarding's default put back to join, the walk failed on
 * the create radio not being checked.
 *
 * **Budget.** `POST /auth/register` and `POST /auth/onboard` are counted in the auth bucket
 * (`docs/contracts/error-codes.md`, "429 and Retry-After"), and the walk attaches what it sent.
 * Read 2026-10-24: 2 counted of 5 browser requests under `/api/v1/auth`.
 *
 * **What it leaves behind.** The identity in the local stack's `auth.users`, as the invitee walk
 * does, and the clan it created with its one membership: no route deletes a clan, and each run
 * names a fresh one, so the seeded clan is untouched.
 */

/** `messages/vi.json`. */
const COPY = {
  fullName: 'Họ và tên',
  email: 'Email',
  password: 'Mật khẩu',
  register: 'Đăng ký',
  clanAfterSignIn: 'Bạn sẽ tạo hoặc tham gia dòng họ sau khi xác nhận email và đăng nhập.',
  signIn: 'Đăng nhập',
  confirmReady: 'Xác nhận địa chỉ email',
  confirmEmail: 'Xác nhận email',
  confirmed: 'Xác thực thành công',
  createClan: 'Tạo dòng họ mới',
  joinClan: 'Tham gia dòng họ',
  clanName: 'Tên dòng họ',
  clanCode: 'Mã dòng họ',
  completeSetup: 'Hoàn tất thiết lập',
} as const

/** `backend/app/i18n/vi.json`, `auth.registration_received`: the 201 body the success screen shows. */
const REGISTRATION_RECEIVED = 'Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp theo'

const PASSWORD = 'sign-up-password-291'
const FULL_NAME = 'Người Đăng Ký 291'

/** A first visit to a route on a cold `next dev` compiles it; see `invitee-registers.auth.spec.ts`. */
const FIRST_VISIT = { timeout: 45_000 }

type ClanMembership = components['schemas']['UserClanMembership']

async function passwordGrant(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<{ access_token: string }> {
  const response = await request.post(
    `${authStackInputs().supabaseUrl}/auth/v1/token?grant_type=password`,
    { headers: { apikey: authStackInputs().supabaseAnonKey }, data: { email, password } },
  )
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()) as { access_token: string }
}

interface AuthRequest {
  method: string
  path: string
  body: unknown
}

/** Every request the browser sent under `/api/v1/auth`, with its body. */
function recordAuthRequests(page: Page): AuthRequest[] {
  const requests: AuthRequest[] = []
  page.on('request', (request) => {
    const { origin, pathname } = new URL(request.url())
    if (origin === authStackInputs().apiOrigin && pathname.startsWith('/api/v1/auth')) {
      requests.push({ method: request.method(), path: pathname, body: request.postDataJSON() })
    }
  })
  return requests
}

/**
 * The routes the backend's auth bucket counts, of those this walk sends
 * (`docs/contracts/error-codes.md`, "429 and Retry-After"). `GET` and `PATCH /auth/me` are not.
 */
const COUNTED = new Set(['POST /api/v1/auth/register', 'POST /api/v1/auth/onboard'])

test.describe('a person with no invitation signs up and creates a clan', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  // Five cold routes at `FIRST_VISIT` each, and a mail to wait for.
  test.setTimeout(300_000)

  test('registers with no clan, confirms, signs in, creates a clan on onboarding and lands on the dashboard', async ({
    page,
    request,
    browser,
    baseURL,
  }) => {
    // Fresh each run: a reused address answers the same 201 and mails a reset instead (ADR-021),
    // and a reused clan code answers `auth.clan_slug_taken`.
    const run = crypto.randomUUID().slice(0, 8)
    const email = `sign-up-291-${run}@familyroots.example.com`
    const clanName = `Dòng họ Thử ${run}`
    const clanCode = `dong-ho-thu-${run}`
    const authRequests = recordAuthRequests(page)

    await test.step('the sign-up form asks for no clan', async () => {
      await page.goto('/vi/register')
      await expect(page.getByLabel(COPY.fullName)).toBeVisible(FIRST_VISIT)
      await expect(page.getByRole('radio'), 'sign-up offers a join/create choice').toHaveCount(0)
      await expect(page.getByLabel(COPY.clanCode)).toHaveCount(0)
      await expect(page.getByText(COPY.clanAfterSignIn)).toBeVisible()
    })

    await test.step('registers with a name, an address and a password, and nothing else', async () => {
      await page.getByLabel(COPY.fullName).fill(FULL_NAME)
      await page.getByLabel(COPY.email, { exact: true }).fill(email)
      await page.getByLabel(COPY.password).fill(PASSWORD)
      await page.getByRole('button', { name: COPY.register, exact: true }).click()

      await expect(page.getByText(REGISTRATION_RECEIVED)).toBeVisible(FIRST_VISIT)
      const registerBodies = authRequests
        .filter(({ method, path }) => method === 'POST' && path === '/api/v1/auth/register')
        .map(({ body }) => body)
      expect(registerBodies).toEqual([{ email, password: PASSWORD, full_name: FULL_NAME }])
    })

    await test.step('confirms the address by the link the local stack mailed', async () => {
      const { link } = await mailedConfirmation(request, email)
      const mailbox = await browser.newContext({ locale: 'vi-VN' })
      try {
        const opened = await mailbox.newPage()
        await opened.goto(onOrigin(link, baseURL))
        await expect(opened.getByRole('heading', { name: COPY.confirmReady })).toBeVisible(
          FIRST_VISIT,
        )
        // Hydrated, so the press reaches its handler (`verify-email-confirm.auth.spec.ts`).
        await opened.waitForLoadState('networkidle')
        await opened.getByRole('button', { name: COPY.confirmEmail }).click()
        await expect(opened.getByRole('heading', { name: COPY.confirmed })).toBeVisible()
      } finally {
        await mailbox.close()
      }
    })

    await test.step('signs in and lands on onboarding, which opens on create', async () => {
      await page.goto('/vi/login')
      await expect(page.getByLabel(COPY.email, { exact: true })).toBeEditable(FIRST_VISIT)
      await page.getByLabel(COPY.email, { exact: true }).fill(email)
      await page.getByLabel(COPY.password).fill(PASSWORD)
      await page.getByRole('button', { name: COPY.signIn, exact: true }).click()

      // `landingPath` sends `needs-onboarding` here.
      await page.waitForURL(
        (url) => url.pathname === '/vi/register' && url.searchParams.get('mode') === 'oauth',
        FIRST_VISIT,
      )
      await expect(page.getByRole('radio', { name: COPY.createClan })).toBeChecked(FIRST_VISIT)
      await expect(page.getByRole('radio', { name: COPY.joinClan })).not.toBeChecked()
    })

    await test.step('creates a clan from its name alone and lands on the dashboard', async () => {
      // The full-name field reads empty here, so the person types the name again. `GET /auth/me`
      // answers `full_name` out of the token's `user_metadata`, which `POST /auth/register` never
      // sets, while the name typed at sign-up sits in `user_profiles.display_name` (ADR-058 § 7).
      // Measured 2026-10-24 on this walk: `full_name: ""` against `display_name` 'Người Đăng Ký
      // 291'. #300 holds the backend fix; the field is required, so without this
      // line the submit never leaves the browser.
      await page.getByLabel(COPY.fullName).fill(FULL_NAME)
      await page.getByLabel(COPY.clanName).fill(clanName)
      await expect(page.getByLabel(COPY.clanCode)).toHaveValue(clanCode)
      await page.getByRole('button', { name: COPY.completeSetup }).click()

      await page.waitForURL((url) => url.pathname === '/vi/dashboard', FIRST_VISIT)
    })

    await test.step('GET /me/clans holds one approved admin membership, in the new clan', async () => {
      const { access_token } = await passwordGrant(request, email, PASSWORD)
      const response = await request.get(`${authStackInputs().apiOrigin}/api/v1/me/clans`, {
        headers: { Authorization: `Bearer ${access_token}` },
      })
      expect(response.status(), await response.text()).toBe(200)
      // `GET /me/clans` lists approved memberships only (`backend/app/api/v1/me.py`).
      const clans = ((await response.json()) as { data: ClanMembership[] }).data
      expect(
        clans.map(({ clan_name, clan_slug, role }) => ({ clan_name, clan_slug, role })),
      ).toEqual([{ clan_name: clanName, clan_slug: clanCode, role: 'admin' }])
    })

    // web/CLAUDE.md, "Budget the requests": a walk counts what it spends and attaches the count.
    const sent = authRequests.map(({ method, path }) => `${method} ${path}`)
    const counted = sent.filter((request) => COUNTED.has(request))
    test.info().annotations.push({
      type: 'rate-limit budget',
      description: `${counted.length} counted (${counted.join(', ')}) of ${sent.length} browser requests under /api/v1/auth: ${sent.join(', ')}`,
    })
  })
})
