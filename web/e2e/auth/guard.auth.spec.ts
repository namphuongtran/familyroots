import { expect, test } from '@playwright/test'
import { SEEDED_USERS } from './fixtures'

/**
 * #186. One server guard routes every signed-in request, by access state and by the capability a
 * page names (`features/auth/server/guard.ts`, ADR-061 § 3-5).
 *
 * **The planted defect each case is meant to fail on.** Written on a machine without Docker, so
 * none of these has been seen to fail yet. The pull request records what each reads.
 *
 * - **The viewer case.** Plant: `admin/users/layout.tsx` calls the guard with no capability. The
 *   viewer is admitted, the reading is `200` instead of `307 → /vi/dashboard`, and the case fails.
 *   The issue's wider plant, a guard that admits everyone, fails the run earlier: the viewer's
 *   capture in `session.setup.ts` reads the same guard on `backoffice/`, and every case here
 *   depends on that project, so they are skipped rather than failed.
 * - **The two super_admin routing cases.** Plant: drop the `platform_role` branch from
 *   `accessStateOf`. The super_admin is read as needing onboarding. `backoffice/` then answers
 *   `307 → /vi/register?mode=oauth`, from the server guard. `/vi/dashboard` ends on
 *   `/vi/register?mode=oauth` too, but by another path: `middleware.ts` sends a user with no clan
 *   cookie to the picker before any guard runs, and the picker routes the state on the client.
 *   The super_admin's capture does not read where the sign-in lands, so the plant reaches these
 *   cases instead of failing the setup.
 *
 * **What this file does not read: the `/platform/metrics` probe.** The guard runs on the Next
 * server, so its requests never appear in a page's network log, and neither did the probe it
 * replaced. A case asserting "no `GET /platform/metrics`" here would pass with the probe restored.
 * `src/features/auth/server/guard.test.ts` records every request the guard sends instead. It
 * failed with the probe put back, run 2026-10-05.
 *
 * One navigation per case: `/api/v1/auth/*` allows 20 requests per 60 seconds per IP by default,
 * and since #186 a guarded load spends two `GET /auth/me`, the guard's on the server and the
 * session query's in the browser, both from this machine's address. A `page.request` read spends
 * one. The harness's backend raises the bucket to 1000 (#226, `web/CLAUDE.md` step 5); this
 * file's super_admin case is the one that read `500` for `307` at 20.
 */

const ADMIN_USERS = '/vi/admin/users'
/** `messages/vi.json`, `admin.users_title`. */
const USERS_TITLE = 'Người dùng dòng họ'
/** `messages/vi.json`, `platform.clans_title`. */
const CLANS_TITLE = 'Tất cả dòng họ'

test.describe('admin/users names viewPendingUsers', () => {
  test.describe('to a viewer', () => {
    test.use({ storageState: SEEDED_USERS.viewer.storageState })

    test('the guard sends them to the dashboard', async ({ page }) => {
      // Read as HTTP, so the redirect is the server guard's and no client effect can supply it.
      const response = await page.request.get(ADMIN_USERS, { maxRedirects: 0 })

      expect(response.status()).toBe(307)
      expect(response.headers()['location']).toMatch(/\/vi\/dashboard$/)
    })
  })

  test.describe('to an admin', () => {
    test.use({ storageState: SEEDED_USERS.admin.storageState })

    test('the guard admits them, and the page renders its heading', async ({ page }) => {
      await page.goto(ADMIN_USERS)

      await expect(page).toHaveURL(new RegExp(`${ADMIN_USERS}$`))
      await expect(page.getByRole('heading', { name: USERS_TITLE })).toBeVisible()
    })
  })
})

test.describe('a super_admin with no clan', () => {
  test.use({ storageState: SEEDED_USERS.superAdmin.storageState })

  test('reaches platform/clans', async ({ page }) => {
    await page.goto('/vi/platform/clans')

    await expect(page).toHaveURL(/\/vi\/platform\/clans$/)
    await expect(page.getByRole('heading', { name: CLANS_TITLE })).toBeVisible()
  })

  test('the guard sends them from a clan route to platform/clans', async ({ page }) => {
    // `backoffice/` carries no clan-cookie gate in the middleware, so this request reaches the
    // server guard, whose `platform` row answers it.
    const response = await page.request.get('/vi/backoffice/dashboard', { maxRedirects: 0 })

    expect(response.status()).toBe(307)
    expect(response.headers()['location']).toMatch(/\/vi\/platform\/clans$/)
  })

  test('opening the dashboard lands on platform/clans, not on onboarding', async ({ page }) => {
    await page.goto('/vi/dashboard')

    await expect(page).toHaveURL(/\/vi\/platform\/clans$/)
    await expect(page.getByRole('heading', { name: CLANS_TITLE })).toBeVisible()
  })
})
