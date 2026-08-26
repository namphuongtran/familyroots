import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Seed S-084: the page an invitation link lands on, driven in a real browser.
 *
 * Three things here cannot be measured anywhere else, which is why this file
 * exists alongside `src/features/invitations/ui/InvitationAcceptScreen.test.tsx`:
 *
 * 1. **The referrer policy.** `<meta name="referrer" content="no-referrer">` is a
 *    browser behaviour. jsdom has no navigation and no `Referer` header, so only an
 *    engine can say whether the token leaks out of this page in one.
 * 2. **The console.** `WebVitalsReporter` (`app/[locale]/layout.tsx:40`) only
 *    reports real Web Vitals, which only a real browser produces.
 * 3. **Layout at 320 px and 200% text scale** (`T-04`,
 *    `.claude/rules/tailwind.md` § 7). jsdom has no layout engine, so no other
 *    harness can measure a box.
 *
 * The backend is stubbed with `page.route`: no e2e spec in this suite talks to a
 * live backend, and the response *codes* are what the page branches on. What the
 * backend does with a token is the backend's own test suite's business.
 */

/** 43 URL-safe base64 characters, the shape `secrets.token_urlsafe(32)` produces. */
const TOKEN = 'Zx-9Qa_bC3dEfGhIjKlMnOpQrStUvWxYz0123456789'

const INVITATION_URL = `/vi/invitations/${TOKEN}`
const ACCEPT_ROUTE = 'http://localhost:8000/api/v1/invitations/*/accept'
const CLAN_ID = '6f1c4f7e-0000-4000-8000-000000000001'

/**
 * The cookie `@supabase/ssr`'s browser client reads a session out of.
 *
 * `createBrowserClient` (`src/lib/supabase/client.ts:11`) stores the session in
 * `document.cookie`, not `localStorage` — that is the point of the SSR package.
 * The name is `sb-${hostname.split('.')[0]}-auth-token`
 * (`node_modules/@supabase/supabase-js/dist/index.mjs:680`), and
 * `playwright.config.ts` gives the e2e server
 * `NEXT_PUBLIC_SUPABASE_URL=https://e2e-fake-project.example.supabase.co`, so the
 * first label is `e2e-fake-project`. The value is `base64-` followed by the
 * base64url of the session JSON (`@supabase/ssr/dist/main/cookies.js:9,45`).
 *
 * Seeding it is the only way to reach the signed-in states in a browser: accept
 * requires a session (`docs/contracts/rest-invitations-api.md:62-64`), and no e2e
 * spec here has a real Supabase to sign in against. Nothing is asserted about
 * Supabase itself — the session is a fixture, and the page's own behaviour is what
 * is measured.
 */
const SESSION_COOKIE_NAME = 'sb-e2e-fake-project-auth-token'

function sessionCookieValue(): string {
  const session = {
    access_token: 'e2e-access-token',
    token_type: 'bearer',
    expires_in: 3600,
    // Far enough out that auth-js never tries a refresh against the fake host.
    expires_at: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 365,
    refresh_token: 'e2e-refresh-token',
    user: {
      id: '9f1c4f7e-0000-4000-8000-0000000000aa',
      aud: 'authenticated',
      role: 'authenticated',
      email: 'invited@example.com',
      app_metadata: {},
      user_metadata: { full_name: 'Người Được Mời' },
      identities: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  }
  return `base64-${Buffer.from(JSON.stringify(session)).toString('base64url')}`
}

async function signIn(page: Page): Promise<void> {
  await page.context().addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: sessionCookieValue(),
      domain: '127.0.0.1',
      path: '/',
    },
  ])
}

function accepted() {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ data: { clan_id: CLAN_ID, role: 'editor', message: 'from backend' } }),
  }
}

function refused(code: string, status: number) {
  return {
    status,
    contentType: 'application/json',
    // A message the page must not render: the UI branches on `code`, never on
    // `message` (`web/CLAUDE.md`).
    body: JSON.stringify({ error: { code, message: 'do not render me', detail: {} } }),
  }
}

async function stubAccept(page: Page, response: Parameters<Route['fulfill']>[0]): Promise<void> {
  await page.route(ACCEPT_ROUTE, (route) => route.fulfill(response))
}

/** Presses Accept once the one-shot session resolve has enabled it. */
async function pressAccept(page: Page): Promise<void> {
  const button = page.getByRole('button', { name: 'Tham gia dòng họ' })
  await expect(button).toBeEnabled()
  await button.click()
}

test.describe('the invitation page, in a browser', () => {
  test('signed out: the page loads with the token still on the URL and asks for sign-in', async ({
    page,
  }) => {
    await page.goto(INVITATION_URL)

    // The route is in `PUBLIC_ROUTES` (`src/middleware.ts`), so the middleware did
    // not redirect to login and take the token with it.
    expect(new URL(page.url()).pathname).toBe(INVITATION_URL)
    await expect(page.getByRole('heading', { name: 'Hãy đăng nhập trước' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/vi/login')
    await expect(page.getByRole('button', { name: 'Tham gia dòng họ' })).toHaveCount(0)
  })

  test('accepted: the page says the invitee joined, and names the granted role', async ({
    page,
  }) => {
    await signIn(page)
    await stubAccept(page, accepted())
    await page.goto(INVITATION_URL)

    await pressAccept(page)

    await expect(page.getByRole('heading', { name: 'Bạn đã tham gia dòng họ' })).toBeVisible()
    await expect(page.getByText('Vai trò của bạn: Chỉnh sửa')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Chọn dòng họ' })).toHaveAttribute(
      'href',
      '/vi/select-clan',
    )
  })

  /**
   * The planted wrong-email control, in a browser. The token is real-shaped, the
   * session is present, and the invited email belongs to somebody else — the case
   * `docs/contracts/rest-invitations-api.md:66-68` exists for. The second half is
   * the half that matters: the success copy must be **absent**.
   */
  test('email_mismatch: the page refuses, and shows no success copy at all', async ({ page }) => {
    await signIn(page)
    await stubAccept(page, refused('invitation.email_mismatch', 403))
    await page.goto(INVITATION_URL)

    await pressAccept(page)

    await expect(page.getByRole('heading', { name: 'Lời mời dành cho email khác' })).toBeVisible()
    await expect(page.getByText('Bạn đã tham gia dòng họ')).toHaveCount(0)
    await expect(page.getByText('Vai trò của bạn')).toHaveCount(0)
    await expect(page.getByText('do not render me')).toHaveCount(0)
  })

  test('expired: the page tells the invitee to ask for a new invitation', async ({ page }) => {
    await signIn(page)
    await stubAccept(page, refused('invitation.expired', 409))
    await page.goto(INVITATION_URL)

    await pressAccept(page)

    await expect(page.getByRole('heading', { name: 'Lời mời đã hết hạn' })).toBeVisible()
    await expect(page.getByText('Bạn đã tham gia dòng họ')).toHaveCount(0)
  })

  test('not_pending: the page says the invitation was already used or revoked', async ({
    page,
  }) => {
    await signIn(page)
    await stubAccept(page, refused('invitation.not_pending', 409))
    await page.goto(INVITATION_URL)

    await pressAccept(page)

    await expect(page.getByRole('heading', { name: 'Lời mời không còn hiệu lực' })).toBeVisible()
    await expect(page.getByText('Bạn đã tham gia dòng họ')).toHaveCount(0)
  })
})

test.describe('the token is treated as a credential', () => {
  test('the page declares no-referrer, and a link followed from it carries none', async ({
    page,
  }) => {
    await page.goto(INVITATION_URL)

    await expect(page.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer')
    // The header is the half that covers the page's own subresources; see the
    // measurement on the next test.
    const response = await page.request.get(INVITATION_URL)
    expect(response.headers()['referrer-policy']).toBe('no-referrer')

    // Follow the one link every refusal state offers. Without the meta tag the
    // default policy (`strict-origin-when-cross-origin`) would send the full
    // same-origin path — token included — as this navigation's `Referer`.
    await page.getByRole('link', { name: 'Đăng nhập' }).click()
    await page.waitForURL('**/vi/login')

    const referrer = await page.evaluate(() => document.referrer)
    expect(referrer).toBe('')
    expect(referrer).not.toContain(TOKEN)
  })

  /**
   * **The measurement that made `next.config.ts` grow a `Referrer-Policy` header.**
   *
   * With only the page's `metadata.referrer` meta tag, this case failed on
   * 2026-08-26 — 31 collected `Referer` values on the first run and 30 on a replant
   * of the control, every one of them
   * `http://127.0.0.1:3100/vi/invitations/<token>` on a `/_next/*` asset request.
   * The count tracks the dev server's chunk count and is not stable; that it is
   * non-zero is.
   * Next.js streams its chunk preloads before the metadata block, so the document
   * has no referrer policy yet when those fetches start. An HTTP response header
   * applies from the first byte; the meta tag does not. The meta tag is still what
   * covers the navigation case in the test above.
   */
  test('no request the page makes carries the token in a Referer header', async ({ page }) => {
    await signIn(page)
    const referers: string[] = []
    page.on('request', (request) => {
      const referer = request.headers()['referer']
      if (referer) referers.push(referer)
    })
    await stubAccept(page, accepted())

    await page.goto(INVITATION_URL)
    await pressAccept(page)
    await expect(page.getByRole('heading', { name: 'Bạn đã tham gia dòng họ' })).toBeVisible()

    // Every subresource this page loads (the app's own chunks, the fonts, the
    // accept POST) is covered: the assertion is over the whole collected set.
    expect(referers.join('\n')).not.toContain(TOKEN)
  })

  test('nothing the page writes to the console carries the token', async ({ page }) => {
    await signIn(page)
    const consoleText: string[] = []
    page.on('console', (message) => consoleText.push(message.text()))
    await stubAccept(page, accepted())

    await page.goto(INVITATION_URL)
    await pressAccept(page)
    await expect(page.getByRole('heading', { name: 'Bạn đã tham gia dòng họ' })).toBeVisible()

    // `WebVitalsReporter` is mounted on every locale route and used to report
    // `window.location.pathname` verbatim, which on this route is the token
    // (seed S-084, `src/shared/telemetry/redact.ts`). Force the metrics out by
    // hiding the page, which is what flushes CLS/LCP/INP.
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await page.waitForTimeout(500)

    expect(consoleText.join('\n')).not.toContain(TOKEN)
    // The control: the token really is in this page's URL, so the assertion above
    // is about the console rather than about a token that was never there.
    expect(page.url()).toContain(TOKEN)
  })
})

/**
 * `T-04`: no horizontal page scroll at 320 dp width and 200% root font size. The
 * shape is `e2e/text-scale.spec.ts`'s, added by seed S-034 — including its trap 4,
 * which is why the scale is set with `addStyleTag` and not by writing to
 * `documentElement.style`.
 */
test.describe('320 dp at 200% text scale', () => {
  const cases = [
    { name: 'the signed-out sign-in state', signedIn: false, press: false },
    { name: 'the accepted state', signedIn: true, press: true },
  ] as const

  for (const outcome of cases) {
    test(`${outcome.name} does not scroll the page sideways`, async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 640 })
      if (outcome.signedIn) await signIn(page)
      await stubAccept(page, accepted())
      await page.goto(INVITATION_URL)
      await page.addStyleTag({ content: ':root { font-size: 32px }' })

      if (outcome.press) {
        await pressAccept(page)
        await expect(page.getByRole('heading', { name: 'Bạn đã tham gia dòng họ' })).toBeVisible()
      } else {
        await expect(page.getByRole('heading', { name: 'Hãy đăng nhập trước' })).toBeVisible()
      }

      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))

      expect(scrollWidth, `scrollWidth ${scrollWidth} vs clientWidth ${clientWidth}`).toBe(
        clientWidth,
      )
    })
  }
})
