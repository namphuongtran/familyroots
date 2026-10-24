import { expect, test, type Page } from '@playwright/test'
import { authStackInputs, SEEDED_USERS } from './fixtures'
import { browserAccessToken } from './session-cookie'

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
/** `messages/vi.json`, `members.add_member` (the list's link) and `member.new_title` (the form's h1). */
const ADD_MEMBER = 'Thêm thành viên'
/** `messages/vi.json`, `member.profile_title`, `member.edit` and `member.edit_title`. */
const PROFILE_TITLE = 'Hồ sơ thành viên'
const EDIT_LINK = 'Chỉnh sửa'
const EDIT_TITLE = 'Chỉnh sửa thành viên'
/** `messages/vi.json`, `member_form.full_name`, `member_form.save_success`, `member_form.continue_label`. */
const FULL_NAME = 'Họ và tên'
const SAVED = 'Đã lưu thay đổi.'
const CONTINUE = 'Tiếp tục'
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

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
  // In order, on one worker: the empty-list case reads that the clan holds no person, and the
  // members walk below creates one (soft-deleting it when it is done).
  test.describe.configure({ mode: 'serial' })

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

  /**
   * Found 2026-10-24 in a manual walk: the content column started 224 px right of the sidebar at
   * every width. `Sidebar` is an in-flow `shrink-0` rail, and the column carried `ml-56` on top,
   * from the March scaffold. The reading is where the column starts, against where the rail ends.
   * Negative control the same day: with `ml-56` put back, `Expected: 224`, `Received: 448`.
   */
  test('the content column starts where the sidebar ends', async ({ page }) => {
    await page.goto('/vi/dashboard')
    await expect(page).toHaveURL(/\/vi\/dashboard$/)

    const rail = await page.locator('aside').first().boundingBox()
    const header = await page.getByRole('banner').boundingBox()
    expect(rail).not.toBeNull()
    expect(header).not.toBeNull()
    expect(Math.round(header!.x)).toBe(Math.round(rail!.x + rail!.width))
  })

  /**
   * Found 2026-10-24 in a manual walk: every link between the persons screens was relative
   * (`./new`, `./${id}`, `./edit`, `..`). A relative URL resolves against the current path's
   * directory, and `/vi/members` has none of its own, so "Thêm thành viên" opened `/vi/new` and a
   * row `/vi/<id>`, both Next's 404, and the profile's edit link `/vi/members/edit`. The walk
   * clicks each link and reads where it lands, by URL and by the heading of the screen there.
   * Negative control the same day: with the seven relative hrefs put back, the walk failed at its
   * first click, `Received string: "http://127.0.0.1:3102/vi/new"`. The person it creates is
   * soft-deleted at the end; a run that fails between the save and the profile leaves it live.
   */
  test('the members screens link to each other: list, new, profile, edit and back', async ({
    page,
    context,
  }) => {
    test.setTimeout(90_000)
    const name = `Người thử điều hướng ${Date.now()}`

    await page.goto('/vi/members')
    await page.getByRole('link', { name: ADD_MEMBER }).click()
    await expect(page).toHaveURL(/\/vi\/members\/new$/)
    await expect(page.getByRole('heading', { name: ADD_MEMBER, level: 1 })).toBeVisible()

    await page.getByLabel(FULL_NAME).fill(name)
    await page.getByRole('button', { name: 'Lưu' }).click()
    await expect(page.getByText(SAVED)).toBeVisible()
    await page.getByRole('button', { name: CONTINUE }).click()
    await expect(page).toHaveURL(new RegExp(`/vi/members/${UUID}$`))
    const id = new URL(page.url()).pathname.split('/').pop()!
    const profile = `/vi/members/${id}`

    try {
      await expect(page.getByRole('heading', { name: PROFILE_TITLE })).toBeVisible()
      await page.getByRole('link', { name: EDIT_LINK }).click()
      await expect(page).toHaveURL(new RegExp(`${profile}/edit$`))
      await expect(page.getByRole('heading', { name: EDIT_TITLE })).toBeVisible()

      // The edit screen's back arrow leads to the profile it came from.
      await page.locator(`main a[href="${profile}"]`).click()
      await expect(page).toHaveURL(new RegExp(`${profile}$`))
      await expect(page.getByRole('heading', { name: PROFILE_TITLE })).toBeVisible()

      // The profile's back arrow leads to the list, and the person's row back to the profile.
      await page.locator('main a[href="/vi/members"]').first().click()
      await expect(page).toHaveURL(/\/vi\/members$/)
      await page.getByRole('link', { name: new RegExp(name) }).click()
      await expect(page).toHaveURL(new RegExp(`${profile}$`))
      await expect(page.getByRole('heading', { name: PROFILE_TITLE })).toBeVisible()
    } finally {
      // Leave the seeded clan as it was, for the empty-list case: soft-delete the person.
      const { apiOrigin } = authStackInputs()
      const token = await browserAccessToken(context)
      const clanId = (await context.cookies()).find((c) => c.name === 'current_clan_id')?.value
      const removed = await page.request.delete(`${apiOrigin}/api/v1/persons/${id}`, {
        headers: { Authorization: `Bearer ${token}`, 'X-Current-Clan-Id': clanId ?? '' },
      })
      expect(removed.status()).toBe(200)
    }
  })
})
