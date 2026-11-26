import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { authStackInputs, SEEDED_USERS } from './fixtures'
import { browserAccessToken } from './session-cookie'

/**
 * #410. Two readings no other authenticated spec takes.
 *
 * 1. The edit form is submitted and the change is read back, on the profile heading and in the
 *    members list row.
 * 2. `/vi/tree` draws a person. The seeded clan has no founder, so every other visit reads the
 *    `Dòng họ chưa có thủy tổ` card. Here a founder is designated with `PUT /clans/me/founder`, a
 *    child is linked through `POST /parent-child`, and the page, loaded fresh, must show one canvas
 *    node per person.
 *
 * Both cases soft-delete what they create, the child before the founder. Soft-deleting the founder
 * puts the clan back in the founder-less state the other specs expect (`tree-read-model.md`).
 * `screen-walk.auth.spec.ts`'s `tree` case asserts only overflow and message keys, so it passes in
 * either state and does not race these.
 */

/** `messages/vi.json`, `member_form.full_name`, `member_form.save_success`, `tree.no_founder_title`. */
const FULL_NAME = 'Họ và tên'
const SAVED = 'Đã lưu thay đổi.'
const NO_FOUNDER = 'Dòng họ chưa có thủy tổ'
const NODE = '[data-person-id]'

interface Api {
  post: (path: string, body: unknown) => Promise<{ id: string }>
  put: (path: string, body: unknown) => Promise<void>
  remove: (path: string) => Promise<void>
}

/** The API as the admin, with the token and clan the browser holds. Call after a page has loaded. */
async function apiAs(page: Page, context: BrowserContext): Promise<Api> {
  const { apiOrigin } = authStackInputs()
  const token = await browserAccessToken(context)
  const clanId = (await context.cookies()).find((c) => c.name === 'current_clan_id')?.value ?? ''
  const headers = { Authorization: `Bearer ${token}`, 'X-Current-Clan-Id': clanId }
  const url = (path: string) => `${apiOrigin}/api/v1${path}`
  return {
    post: async (path, body) => {
      const response = await page.request.post(url(path), { headers, data: body })
      expect(response.status(), `POST ${path}`).toBe(201)
      return ((await response.json()) as { data: { id: string } }).data
    },
    put: async (path, body) => {
      const response = await page.request.put(url(path), { headers, data: body })
      expect(response.status(), `PUT ${path}`).toBe(200)
    },
    remove: async (path) => {
      const response = await page.request.delete(url(path), { headers })
      expect(response.status(), `DELETE ${path}`).toBe(200)
    },
  }
}

test.describe('person edit and the rendered tree, as an admin', () => {
  test.use({ storageState: SEEDED_USERS.admin.storageState })
  test.describe.configure({ mode: 'serial' })

  test('editing a full name saves, and the profile and the list read the new name', async ({
    page,
    context,
  }) => {
    test.setTimeout(90_000)
    const stamp = Date.now()
    const before = `Người trước khi sửa ${stamp}`
    const after = `Người sau khi sửa ${stamp}`

    await page.goto('/vi/dashboard')
    const api = await apiAs(page, context)
    const { id } = await api.post('/persons', { full_name: before, gender: 'unknown' })

    try {
      await page.goto(`/vi/members/${id}/edit`)
      const name = page.getByLabel(FULL_NAME)
      await expect(name).toHaveValue(before)
      await name.fill(after)
      await page.getByRole('button', { name: 'Lưu' }).click()
      await expect(page.getByText(SAVED)).toBeVisible()

      // Fresh loads, so the reading is the server's and not the form's own state.
      await page.goto(`/vi/members/${id}`)
      await expect(page.getByRole('heading', { level: 1, name: after })).toBeVisible()
      await page.goto('/vi/members')
      await expect(page.getByRole('link', { name: new RegExp(after) })).toBeVisible()
      await expect(page.getByText(before)).toHaveCount(0)
    } finally {
      await api.remove(`/persons/${id}`)
    }
  })

  test('a founder and a linked child are two nodes on the /vi/tree canvas', async ({
    page,
    context,
  }) => {
    test.setTimeout(90_000)
    const stamp = Date.now()
    const founderName = `Thủy tổ thử cây ${stamp}`
    const childName = `Con của thủy tổ ${stamp}`

    await page.goto('/vi/dashboard')
    const api = await apiAs(page, context)
    const founder = await api.post('/persons', { full_name: founderName, gender: 'male' })
    let childId: string | null = null

    try {
      const child = await api.post('/persons', { full_name: childName, gender: 'male' })
      childId = child.id
      await api.put('/clans/me/founder', { person_id: founder.id })
      await api.post('/parent-child', {
        parent_id: founder.id,
        child_id: child.id,
        relationship_type: 'biological',
      })

      await page.goto('/vi/tree')
      await expect(page.getByText(NO_FOUNDER)).toHaveCount(0)
      const node = (name: string) =>
        page.locator(NODE).filter({ has: page.getByText(name, { exact: true }) })
      await expect(node(founderName)).toHaveCount(1)
      await expect(node(childName)).toHaveCount(1)
      await expect(page.locator(NODE)).toHaveCount(2)
    } finally {
      // The child first, then the founder: the founder's removal re-404s the tree.
      if (childId !== null) await api.remove(`/persons/${childId}`)
      await api.remove(`/persons/${founder.id}`)
    }
  })
})
