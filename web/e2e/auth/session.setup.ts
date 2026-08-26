import { expect, test as setup } from '@playwright/test'
import { SEEDED_PASSWORD, SEEDED_USERS, type SeededUser } from './fixtures'

/**
 * Seed S-070. The only place in this repository that turns credentials into a session, and
 * it does it the way a member does: it types into `/vi/login` and presses the button.
 *
 * **Why a real login rather than a signed token or a stubbed `getSession`.** The maintainer
 * chose the full Supabase CLI stack on 2026-08-22 (S-070's own text), and the two rejected
 * options are rejected here too. Minting a JWT in the test would exercise none of
 * `LoginPage` → `useAuthActions.signIn` → `@supabase/ssr`'s cookie writer →
 * `middleware.ts`'s session check → `requireServerRole`'s call to `GET /me/clans`, which is
 * the chain no test had ever executed. A stub at `requireServerRole` would put a
 * session-shaped hole in shipped code, which S-070 forbids in as many words.
 *
 * **Each setup ends on a reading, not on a file write.** A login that succeeds at Supabase
 * and then reaches nothing would otherwise leave a storage-state file that looks fine and a
 * suite full of redirects to `/vi/login`. The admin's last act is rendering the gated
 * screen; the viewer's is being refused it *by role* rather than for want of a session,
 * which is a different HTTP answer and is checked as one.
 */

const BACKOFFICE_PATH = '/vi/backoffice/dashboard'

/**
 * `middleware.ts` sends a request with no session to `/{locale}/login`, and
 * `requireServerRole` sends an authenticated user with too low a role to
 * `/{locale}/dashboard`. Those two Locations are how a "refused" reading is told apart from
 * a "no session at all" reading — the distinction `.claude/rules/seeds.md` demands when it
 * says the failing reading must differ from the passing one.
 */
const DASHBOARD_LOCATION = /\/vi\/dashboard$/

async function signIn(page: import('@playwright/test').Page, user: SeededUser): Promise<void> {
  await page.goto('/vi/login')

  // The two inputs carry no `id` and their `<label>`s carry no `htmlFor`
  // (`src/app/[locale]/(auth)/login/page.tsx`), so `getByLabel` finds nothing. Selecting by
  // input type is what `e2e/dark-theme.spec.ts` already does on this same form. That missing
  // label association is a real a11y defect; S-070 reports it and does not fix it.
  await page.locator('input[type="email"]').fill(user.email)
  await page.locator('input[type="password"]').fill(SEEDED_PASSWORD)
  await page.locator('form button[type="submit"]').click()

  /**
   * Waiting for the Supabase cookie rather than for a URL, and then leaving at once.
   *
   * `signInWithEmail` pushes to `/vi/dashboard`, and **that screen currently runs away**:
   * measured 2026-08-26, `/vi/dashboard` re-ran `useAuth`'s mount effect 2613 times in
   * seven seconds and issued 18174 `GET /auth/me` calls until the backend's
   * 20-per-60-second limiter on `/api/v1/auth/*` (`backend/app/main.py:221-226`) began
   * answering 429. That defect is reported by S-070 and is not S-070's to fix — see
   * `web/CLAUDE.md`, "The `(dashboard)` group runs away". This harness therefore does not
   * linger there: the cookie appears while `signInWithEmail` is still resolving, so polling
   * for it lets the setup navigate away before the loop has a page to run on.
   */
  await expect
    .poll(
      async () => {
        const cookies = await page.context().cookies()
        return cookies.some((c) => c.name.startsWith('sb-') && c.name.endsWith('-auth-token'))
      },
      { timeout: 30_000, intervals: [100] },
    )
    .toBe(true)
}

setup('capture a real admin session, ending on the gated screen', async ({ page }) => {
  const user = SEEDED_USERS.admin
  await signIn(page, user)

  await page.goto(BACKOFFICE_PATH)

  // `page.goto` resolves on a redirect too, so the URL is read as well as the heading: a
  // bounce to `/vi/login` or `/vi/dashboard` would otherwise leave a green setup.
  await expect(page).toHaveURL(new RegExp(`${BACKOFFICE_PATH}$`))
  await expect(page.locator('main h1')).toBeVisible({ timeout: 15_000 })

  await page.context().storageState({ path: user.storageState })
})

setup('capture a real viewer session, refused the gated screen by role', async ({ page }) => {
  const user = SEEDED_USERS.viewer
  await signIn(page, user)

  // No navigation: `page.request` shares this context's cookies and runs no page JavaScript,
  // so the role gate is read without mounting anything. `requireServerRole` answers a
  // logged-in viewer with a redirect to the dashboard — proof both that the session is real
  // and that the gate saw a role it refused.
  const refused = await page.request.get(BACKOFFICE_PATH, { maxRedirects: 0 })
  expect(refused.status()).toBe(307)
  expect(refused.headers()['location']).toMatch(DASHBOARD_LOCATION)

  await page.context().storageState({ path: user.storageState })
})
