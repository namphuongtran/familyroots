import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { authStackInputs, SEEDED_PASSWORD } from './fixtures'
import {
  mailIdsFor,
  newMail,
  onOrigin,
  readsVietnameseFirst,
  tokenHashLink,
  type Headings,
} from './mail'
import { browserAccessToken } from './session-cookie'

/**
 * #201, ADR-063. A seeded member who has forgotten their password asks for a reset from the
 * sign-in screen, opens the link the local stack mailed, sets a new password, and signs in with
 * it. One test in steps, because every step acts on the one account.
 *
 * **The user is `editor@`**, a seeded member of `nguyen-phuc` that no setup signs in as, so a run
 * that stops before it restores the password breaks no other spec. `make seed` would not repair
 * it: the seeder cannot read a password back (`docs/ops/seed-test-users.md`).
 *
 * **The link is the one the local stack mailed** (#202). The stack renders
 * `supabase/templates/recovery.html`, which links
 * `{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}&type=recovery` (ADR-063 § 1). The walk
 * checks that shape and that the mail reads Vietnamese first, then opens the link with the
 * harness's origin in place of the Site URL's, the path and query unchanged. The middleware sends
 * the locale-less path to `/vi/reset-password` with the query kept. A successful verify is what
 * proves the hash right. The seeded inbox keeps earlier runs' mail, so the walk reads the one mail
 * that arrived after its own request.
 *
 * **Signing out is local**: the walk clears the browser's cookies, which is where `@supabase/ssr`
 * keeps the session and what `signOut({ scope: 'local' })` removes. No screen the walk reaches
 * offers a sign-out: `Tiếp tục` leads to the clan picker, because nothing set the clan cookie.
 *
 * **The control is the same link, submitted again.** The token is spent, so GoTrue answers 403 and
 * the page shows the expired state, with no second update sent.
 *
 * **What it leaves behind**: one more recovery mail in Mailpit. The password is put back to
 * `SEEDED_PASSWORD` through GoTrue in a `finally`, whatever step failed. **Budget**: one
 * `POST /auth/forgot-password`, one `GET /auth/me` from the test, and one sign-in's reads.
 */

/** `messages/vi.json`. */
const COPY = {
  forgotLink: 'Quên mật khẩu?',
  forgotHeading: 'Quên mật khẩu',
  email: 'Email',
  forgotSubmit: 'Gửi thư đặt lại mật khẩu',
  forgotSent:
    'Nếu địa chỉ này có tài khoản, chúng tôi đã gửi tới đó một thư hướng dẫn đặt lại mật khẩu. Xin kiểm tra hộp thư của bạn.',
  resetHeading: 'Đặt mật khẩu mới',
  newPassword: 'Mật khẩu mới',
  resetSubmit: 'Lưu mật khẩu mới',
  resetSuccess: 'Đã đặt mật khẩu mới',
  expired: 'Liên kết đã hết hạn',
  requestNew: 'Yêu cầu liên kết mới',
  password: 'Mật khẩu',
  signIn: 'Đăng nhập',
} as const

const EDITOR = 'editor@familyroots.example.com'

/** `supabase/templates/recovery.html`: its Vietnamese heading, then its English one. */
const MAIL: Headings = { vi: 'Đặt lại mật khẩu', en: 'Reset your password' }

/** A cold `next dev` compiles a route on its first visit (web/CLAUDE.md, "The authenticated e2e harness"). */
const FIRST_VISIT = { timeout: 45_000 }

/** Every request the page sends to GoTrue's verify and user endpoints, in order. */
function recordGoTrue(page: Page): () => string[] {
  const sent: string[] = []
  page.on('request', (request) => {
    const { pathname } = new URL(request.url())
    if (request.method() === 'POST' && pathname === '/auth/v1/verify') sent.push('verify')
    if (request.method() === 'PUT' && pathname === '/auth/v1/user') sent.push('update')
  })
  return () => [...sent]
}

/** Types into `/vi/login` and presses the button, answering with the password grant's status. */
async function signIn(page: Page, password: string): Promise<number> {
  await page.goto('/vi/login')
  await page.getByLabel(COPY.email).fill(EDITOR)
  await page.getByLabel(COPY.password, { exact: true }).fill(password)
  const grant = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === '/auth/v1/token' &&
      response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: COPY.signIn, exact: true }).click()
  return (await grant).status()
}

/**
 * Puts the seeded password back, through GoTrue as the user. A no-op when `password` no longer
 * signs in, which is the case when the walk stopped before it changed anything.
 */
async function restoreSeededPassword(request: APIRequestContext, password: string): Promise<void> {
  const { supabaseUrl, supabaseAnonKey } = authStackInputs()
  const headers = { apikey: supabaseAnonKey }
  const grant = await request.post(`${supabaseUrl}/auth/v1/token?grant_type=password`, {
    headers,
    data: { email: EDITOR, password },
  })
  if (!grant.ok()) return
  const { access_token } = (await grant.json()) as { access_token: string }
  const update = await request.put(`${supabaseUrl}/auth/v1/user`, {
    headers: { ...headers, Authorization: `Bearer ${access_token}` },
    data: { password: SEEDED_PASSWORD },
  })
  expect(update.status(), `restoring ${EDITOR}'s seeded password: ${await update.text()}`).toBe(200)
}

test.describe('a member resets a forgotten password through /vi/forgot-password', () => {
  // No session: the person has forgotten their password.
  test.use({ storageState: { cookies: [], origins: [] } })
  test.setTimeout(240_000)

  test('the reset spends its token on the submit, and only the new password signs in', async ({
    page,
    request,
    baseURL,
  }) => {
    const newPassword = `reset-201-${crypto.randomUUID()}`
    const goTrue = recordGoTrue(page)
    let resetLink = ''
    let tokenQuery = ''

    try {
      await test.step('asks for a reset from the sign-in screen', async () => {
        const seen = await mailIdsFor(request, EDITOR)
        await page.goto('/vi/login')
        await page.getByRole('link', { name: COPY.forgotLink }).click(FIRST_VISIT)
        await expect(page).toHaveURL(/\/vi\/forgot-password$/, FIRST_VISIT)
        await expect(page.getByRole('heading', { name: COPY.forgotHeading })).toBeVisible()

        await page.getByLabel(COPY.email).fill(EDITOR)
        const forgot = page.waitForResponse(
          (response) => new URL(response.url()).pathname === '/api/v1/auth/forgot-password',
        )
        await page.getByRole('button', { name: COPY.forgotSubmit }).click()
        expect((await forgot).status()).toBe(200)
        await expect(page.getByRole('status')).toHaveText(COPY.forgotSent)

        const mail = await newMail(request, EDITOR, seen)
        const { tokenHash, search } = tokenHashLink(mail, '/reset-password', 'recovery')
        expect(readsVietnameseFirst(mail, MAIL), 'the mail reads Vietnamese first').toBe(true)
        test.info().annotations.push({
          type: 'what the local stack sent',
          description: `subject "${mail.subject}"; ${mail.text.replaceAll(tokenHash, '<token_hash>')}`,
        })
        // The harness's origin stands in for the Site URL's, where nothing listens (`mail.ts`).
        resetLink = onOrigin(mail.link, baseURL)
        tokenQuery = search
      })

      await test.step('loading the reset page spends nothing', async () => {
        await page.goto(resetLink)
        await expect(page.getByRole('heading', { name: COPY.resetHeading })).toBeVisible(
          FIRST_VISIT,
        )
        // The link carries no locale; the reader's is Vietnamese, and the query survived the redirect.
        expect(new URL(page.url()).pathname).toBe('/vi/reset-password')
        expect(new URL(page.url()).search).toBe(tokenQuery)
        // Hydrated, so a submit reaches the handler, and long enough for a mount effect to send.
        await page.waitForLoadState('networkidle')
        expect(goTrue()).toEqual([])
      })

      await test.step('one submit verifies, then sets the new password', async () => {
        await page.getByLabel(COPY.newPassword).fill(newPassword)
        await page.getByRole('button', { name: COPY.resetSubmit }).click()
        await expect(page.getByRole('heading', { name: COPY.resetSuccess })).toBeVisible()
        expect(goTrue()).toEqual(['verify', 'update'])
      })

      await test.step('the session it kept is one the backend accepts', async () => {
        const accessToken = await browserAccessToken(page.context())
        const response = await request.get(`${authStackInputs().apiOrigin}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        expect(response.status(), await response.text()).toBe(200)
        const { data } = (await response.json()) as { data: { email: string } }
        expect(data.email).toBe(EDITOR)
      })

      await test.step('signs out, and the old password is refused', async () => {
        await page.context().clearCookies()
        expect(await signIn(page, SEEDED_PASSWORD)).toBe(400)
        await expect(page).toHaveURL(/\/vi\/login$/)
      })

      await test.step('the new password signs in', async () => {
        expect(await signIn(page, newPassword)).toBe(200)
        await expect(page).toHaveURL(/\/vi\/dashboard$/, FIRST_VISIT)
      })

      await test.step('the same link, submitted again, reads expired', async () => {
        await page.goto(resetLink)
        await expect(page.getByRole('heading', { name: COPY.resetHeading })).toBeVisible()
        await page.waitForLoadState('networkidle')
        await page.getByLabel(COPY.newPassword).fill(`${newPassword}-again`)
        await page.getByRole('button', { name: COPY.resetSubmit }).click()
        await expect(page.getByRole('heading', { name: COPY.expired })).toBeVisible()
        await expect(page.getByRole('link', { name: COPY.requestNew })).toHaveAttribute(
          'href',
          '/vi/forgot-password',
        )
        expect(goTrue()).toEqual(['verify', 'update', 'verify'])
      })
    } finally {
      await restoreSeededPassword(request, newPassword)
    }
  })
})
