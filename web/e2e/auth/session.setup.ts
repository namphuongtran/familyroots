import { expect, test as setup } from '@playwright/test'
import { SEEDED_PASSWORD, SEEDED_USERS, type SeededUser } from './fixtures'

/**
 * the authenticated e2e harness. The only place in this repository that turns credentials into a session, and
 * it does it the way a member does: it types into `/vi/login` and presses the button.
 *
 * **Why a real login rather than a signed token or a stubbed `getSession`.** The maintainer
 * chose the full Supabase CLI stack on 2026-08-22 (the authenticated e2e harness's own text), and the two rejected
 * options are rejected here too. Minting a JWT in the test would exercise none of
 * `LoginPage` → `useAuthActions.signIn` → `@supabase/ssr`'s cookie writer →
 * `middleware.ts`'s session check → the server guard's `GET /auth/me` and `GET /me/clans`
 * (`features/auth/server/guard.ts`, #186; `requireServerRole` until then), which is the chain
 * no test had ever executed. A stub at the guard would put a session-shaped hole in shipped
 * code, which the authenticated e2e harness forbids in as many words.
 *
 * **Each setup ends on a reading, not on a file write.** A login that succeeds at Supabase
 * and then reaches nothing would otherwise leave a storage-state file that looks fine and a
 * suite full of redirects to `/vi/login`. The admin's last act is rendering the gated
 * screen; the viewer's is being refused it *by role* rather than for want of a session,
 * which is a different HTTP answer and is checked as one. The super_admin's is the platform
 * screen, which the guard admits only on `platform_role` read from `GET /auth/me`.
 */

const BACKOFFICE_PATH = '/vi/backoffice/dashboard'

/** `messages/vi.json`, `platform.clans_title`. */
const PLATFORM_CLANS_TITLE = 'Tất cả dòng họ'

/**
 * `middleware.ts` sends a request with no session to `/{locale}/login`, and the server guard
 * sends an authenticated member without the page's capability to `/{locale}/dashboard`. Those
 * two Locations are how a "refused" reading is told apart from a "no session at all" reading —
 * the distinction `.claude/rules/testing.md` demands when it says the failing reading must
 * differ from the passing one.
 */
const DASHBOARD_LOCATION = /\/vi\/dashboard$/

/**
 * **A setup is the first visit to every route it reads, and a run starts its own server.** On a
 * cold `next dev` the first request to a route compiles it. With no `.next-auth-e2e` cache, read
 * 2026-10-07 (#226): `GET /vi/login` in 19.7 s, `/vi/dashboard` in 15.9 s, `/vi/platform/clans`
 * in 16.2 s, the three setups compiling at once. Each setup reads two or three such routes, so
 * Playwright's default 30 s for the whole test failed two of the three that day, on a server no
 * one had warmed. Each first reading waits `FIRST_VISIT`, the invitee walk's figure, and the
 * test as a whole three of them. A warm route answers in about a second, so neither bound is
 * reached on a warm server, and a sign-in that truly fails still fails, on the same reading.
 */
const FIRST_VISIT = { timeout: 45_000 }
setup.describe.configure({ timeout: 3 * FIRST_VISIT.timeout })

async function signIn(page: import('@playwright/test').Page, user: SeededUser): Promise<void> {
  await page.goto('/vi/login')

  // The two inputs carry no `id` and their `<label>`s carry no `htmlFor`
  // (`src/app/[locale]/(auth)/login/page.tsx`), so `getByLabel` finds nothing. Selecting by
  // input type is what `e2e/dark-theme.spec.ts` already does on this same form. That missing
  // label association is a real a11y defect; the authenticated e2e harness reports it and does not fix it.
  await page.locator('input[type="email"]').fill(user.email)
  await page.locator('input[type="password"]').fill(SEEDED_PASSWORD)
  await page.locator('form button[type="submit"]').click()

  /**
   * Waiting for the sign-in to leave the form, which it does only after Supabase has written the
   * cookie and the session has been read. Where it lands is each setup's own reading below, not
   * this helper's: the super_admin's landing goes through `accessStateOf`, and #186's negative
   * control breaks that function on purpose, which must fail a case in `guard.auth.spec.ts`
   * rather than this setup.
   *
   * Until #183 this polled for the Supabase cookie and left at once, because `/vi/dashboard` ran
   * away: 9037 `GET /auth/me` in twelve seconds, measured 2026-10-04, until the backend's
   * 20-per-60-second limiter on `/api/v1/auth/*` answered 429. `dashboard.auth.spec.ts` counts
   * the requests.
   */
  await expect(page).not.toHaveURL(/\/vi\/login$/, FIRST_VISIT)
  const cookies = await page.context().cookies()
  expect(cookies.some((c) => c.name.startsWith('sb-') && c.name.endsWith('-auth-token'))).toBe(true)
}

/** Each member holds one approved membership, in `nguyen-phuc`, so a sign-in lands here. */
const MEMBER_LANDING = /\/vi\/dashboard$/

setup('capture a real admin session, ending on the gated screen', async ({ page }) => {
  const user = SEEDED_USERS.admin
  await signIn(page, user)
  await expect(page).toHaveURL(MEMBER_LANDING)

  await page.goto(BACKOFFICE_PATH)

  // `page.goto` resolves on a redirect too, so the URL is read as well as the heading: a
  // bounce to `/vi/login` or `/vi/dashboard` would otherwise leave a green setup.
  await expect(page).toHaveURL(new RegExp(`${BACKOFFICE_PATH}$`))
  await expect(page.locator('main h1')).toBeVisible(FIRST_VISIT)

  await page.context().storageState({ path: user.storageState })
})

setup('capture a real viewer session, refused the gated screen by role', async ({ page }) => {
  const user = SEEDED_USERS.viewer
  await signIn(page, user)
  await expect(page).toHaveURL(MEMBER_LANDING)

  // No navigation: `page.request` shares this context's cookies and runs no page JavaScript,
  // so the role gate is read without mounting anything. The guard answers a logged-in viewer,
  // who lacks `viewPendingUsers`, with a redirect to the dashboard — proof both that the
  // session is real and that the gate saw a role it refused.
  const refused = await page.request.get(BACKOFFICE_PATH, { maxRedirects: 0, ...FIRST_VISIT })
  expect(refused.status()).toBe(307)
  expect(refused.headers()['location']).toMatch(DASHBOARD_LOCATION)

  await page.context().storageState({ path: user.storageState })
})

setup('capture a real super_admin session, with no clan, ending on platform/', async ({ page }) => {
  const user = SEEDED_USERS.superAdmin
  await signIn(page, user)

  // The platform layout's guard admits the request only if `GET /auth/me` said
  // `platform_role: "super_admin"`, and sends anyone else away. The guard reads the profile, not
  // the access state, so where the sign-in itself landed is left to `guard.auth.spec.ts`.
  await page.goto('/vi/platform/clans')
  await expect(page).toHaveURL(/\/vi\/platform\/clans$/)
  await expect(page.getByRole('heading', { name: PLATFORM_CLANS_TITLE })).toBeVisible(FIRST_VISIT)

  await page.context().storageState({ path: user.storageState })
})
