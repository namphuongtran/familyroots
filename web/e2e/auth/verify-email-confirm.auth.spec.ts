import { expect, test, type Page } from '@playwright/test'
import { authStackInputs } from './fixtures'
import { mailedConfirmation } from './mail'
import { browserAccessToken } from './session-cookie'

/**
 * #200, ADR-063. A person confirms a new address on `/vi/verify-email/confirm`, and the session
 * the confirmation hands back is one the backend accepts.
 *
 * **The link is built here, from what the local stack mailed.** Until the template issue (#202)
 * reaches the local stack, its confirmation mail is Supabase's default: one link to GoTrue's own
 * `/auth/v1/verify?token=…&type=signup&redirect_to=…`. That `token` is the token hash, the value
 * `{{ .TokenHash }}` will carry, because GoTrue builds the default link from the hash it stores
 * (56 hex characters, a SHA-224). So this walk reads `token` off that link and opens
 * `/vi/verify-email/confirm?token_hash=<it>&type=email`. A successful verify is what proves the
 * value was right; a wrong one reads as the expired state, and the success step fails.
 *
 * **What the local stack sent is attached** to each run as an annotation, with the hash replaced.
 * `supabase/config.toml` sets `enable_confirmations = false`, but the backend creates the identity
 * unconfirmed and then asks GoTrue to resend the sign-up mail (`supabase_identity_provider.py`),
 * so the mail is sent anyway, as `invitee-registers.auth.spec.ts` found for #196.
 *
 * **The session is the browser's, read where the browser keeps it.** `@supabase/ssr` writes the
 * session to the `sb-<ref>-auth-token` cookie, in chunks when it is long. The walk reads the
 * access token from that cookie and sends it to `GET /auth/me`, so a 200 there is the session
 * this page kept, not one the test made.
 *
 * **The control is the same link, pressed again.** The token is spent, so GoTrue answers 403
 * `otp_expired` and the page shows the expired state. If the second press read as a success, the
 * first reading would mean nothing.
 *
 * **What it leaves behind.** The identity stays in the local stack's `auth.users` and the
 * backend's `users`, with no clan: the harness holds no service-role key, and each run uses a
 * fresh address. **Budget**: one `POST /auth/register` and one `GET /auth/me` from the bucket.
 */

/** `messages/vi.json`. */
const COPY = {
  ready: 'Xác nhận địa chỉ email',
  confirm: 'Xác nhận email',
  success: 'Xác thực thành công',
  expired: 'Liên kết đã hết hạn',
  resend: 'Gửi lại thư xác thực',
} as const

const PASSWORD = 'confirm-password-200'

/** A cold `next dev` compiles a route on its first visit (web/CLAUDE.md, "The authenticated e2e harness"). */
const FIRST_VISIT = { timeout: 45_000 }

/** Every `POST /auth/v1/verify` the page sends, from the moment this is called. */
function countVerify(page: Page): () => number {
  let count = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/auth/v1/verify') {
      count += 1
    }
  })
  return () => count
}

test.describe('a person confirms a new address on /vi/verify-email/confirm', () => {
  // No session: the person who opens the mail has not signed in.
  test.use({ storageState: { cookies: [], origins: [] } })
  test.setTimeout(180_000)

  test('loading spends nothing, a press confirms and keeps the session, a second press reads expired', async ({
    page,
    request,
  }) => {
    const email = `confirm-200-${crypto.randomUUID()}@familyroots.example.com`
    const verifies = countVerify(page)
    let confirmPath = ''

    await test.step('registers through POST /auth/register', async () => {
      const response = await request.post(`${authStackInputs().apiOrigin}/api/v1/auth/register`, {
        data: { email, password: PASSWORD, full_name: 'Người Xác Nhận 200' },
      })
      expect(response.status(), await response.text()).toBe(201)
    })

    await test.step('derives the token hash from the mail the local stack sent', async () => {
      const mail = await mailedConfirmation(request, email)
      const link = new URL(mail.link)
      const tokenHash = link.searchParams.get('token') ?? ''
      expect(tokenHash, `the default link's token is the hash: ${mail.link}`).toMatch(
        /^[0-9a-f]{56}$/,
      )
      test.info().annotations.push({
        type: 'what the local stack sent',
        description: `subject "${mail.subject}"; ${mail.text.replaceAll(tokenHash, '<token_hash>')}`,
      })
      confirmPath = `/vi/verify-email/confirm?token_hash=${tokenHash}&type=email`
    })

    await test.step('loading the page spends nothing', async () => {
      await page.goto(confirmPath)
      await expect(page.getByRole('heading', { name: COPY.ready })).toBeVisible(FIRST_VISIT)
      // Hydrated, so a press reaches the handler, and long enough for a mount effect to send.
      await page.waitForLoadState('networkidle')
      expect(verifies()).toBe(0)
    })

    await test.step('a press confirms the address, once', async () => {
      await page.getByRole('button', { name: COPY.confirm }).click()
      await expect(page.getByRole('heading', { name: COPY.success })).toBeVisible()
      expect(verifies()).toBe(1)
    })

    await test.step('GET /auth/me answers 200 with the browser’s session', async () => {
      const accessToken = await browserAccessToken(page.context())
      const response = await request.get(`${authStackInputs().apiOrigin}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      expect(response.status(), await response.text()).toBe(200)
      const { data } = (await response.json()) as { data: { email: string } }
      expect(data.email).toBe(email)
    })

    await test.step('the same link, pressed again, reads expired', async () => {
      await page.goto(confirmPath)
      await expect(page.getByRole('heading', { name: COPY.ready })).toBeVisible()
      await page.waitForLoadState('networkidle')
      await page.getByRole('button', { name: COPY.confirm }).click()
      await expect(page.getByRole('heading', { name: COPY.expired })).toBeVisible()
      await expect(page.getByRole('link', { name: COPY.resend })).toHaveAttribute(
        'href',
        '/vi/verify-email',
      )
      expect(verifies()).toBe(2)
    })
  })
})
