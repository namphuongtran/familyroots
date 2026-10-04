import { expect, test, type Page } from '@playwright/test'
import { SEEDED_USERS } from './fixtures'

/**
 * #183. The `(dashboard)` group, read with a real session now that the session is one query.
 *
 * **The runaway this replaces.** Measured 2026-08-26, `/vi/dashboard` re-ran the legacy
 * `useAuth` mount effect 2613 times in seven seconds and sent 18174 `GET /auth/me`. The layout
 * and `Header` each hydrated on their own and wrote fresh objects into a zustand store, which
 * re-ran both. `web/CLAUDE.md`, "The `(dashboard)` group runs away", has the account and the
 * reading this file took before the change.
 *
 * **Why a count, and why exactly one.** Every consumer of the session now reads one TanStack
 * Query cache entry, so the number of `GET /auth/me` a load sends is fixed by design, not by
 * how many components happen to mount. The layout, `Sidebar` and `Header` each read it.
 *
 * #183 set the bound at "at most 2", with a planted defect that had to push it above that:
 * `Header` reading the session under its own query key. Planted on 2026-10-04, that defect sends
 * **2**, one per key, and "at most 2" passed it. A bound the defect it names cannot cross pins
 * nothing (`.claude/rules/testing.md`, question 2), so the bound is the measured 1, and the same
 * plant now fails it. Before #183 the same load sent 9037 in twelve seconds.
 */

const AUTH_ME = '/api/v1/auth/me'
/** `messages/vi.json`, `members.page_title`. */
const MEMBERS_TITLE = 'Thành viên'
/** `messages/vi.json`, `members.no_members`: `make seed` writes no persons. */
const NO_MEMBERS = 'Chưa có thành viên nào'

/** Every `GET /auth/me` the page sends, from the moment this is called. */
function countAuthMe(page: Page): () => number {
  let count = 0
  page.on('request', (request) => {
    if (request.method() === 'GET' && new URL(request.url()).pathname === AUTH_ME) count += 1
  })
  return () => count
}

test.describe('the (dashboard) group, as an admin', () => {
  test.use({ storageState: SEEDED_USERS.admin.storageState })

  test('one dashboard load sends one GET /auth/me, however many components read the session', async ({
    page,
  }) => {
    const authMeCount = countAuthMe(page)

    await page.goto('/vi/dashboard')
    // The URL as well as the count: a redirect to /vi/login sends no `GET /auth/me` at all.
    await expect(page).toHaveURL(/\/vi\/dashboard$/)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(5_000)

    const count = authMeCount()
    test.info().annotations.push({ type: 'GET /auth/me', description: String(count) })
    expect(count).toBe(1)
  })

  test('/vi/members renders the persons list', async ({ page }) => {
    const persons = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' &&
        new URL(response.url()).pathname === '/api/v1/persons',
    )

    await page.goto('/vi/members')

    await expect(page).toHaveURL(/\/vi\/members$/)
    // The list's own answer, not the page shell: the request it sends succeeds, and what it
    // renders is the empty state rather than its error state or its skeleton.
    expect((await persons).status()).toBe(200)
    await expect(page.getByRole('heading', { name: MEMBERS_TITLE })).toBeVisible()
    await expect(page.getByText(NO_MEMBERS)).toBeVisible()
  })
})
