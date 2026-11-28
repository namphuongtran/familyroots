import { readFileSync } from 'node:fs'
import path from 'node:path'
import { expect, test, devices, type Browser, type Page } from '@playwright/test'
import { AUTH_BASE_URL } from '../../playwright.config'
import { authStackInputs, SEEDED_USERS } from './fixtures'
import { browserAccessToken } from './session-cookie'

/**
 * #371. Every authenticated route the app serves, read at a phone and at a desktop, in the light
 * and the dark theme, as an admin.
 *
 * Three readings per page and combination, none of them a setting (`.claude/rules/testing.md`):
 *
 * 1. no horizontal overflow, `document.documentElement.scrollWidth <= clientWidth`;
 * 2. no visible text that is a message key. next-intl renders a missing message as its
 *    `namespace.key` path, so the reading is "visible text contains a top-level namespace of
 *    `messages/vi.json` followed by a dotted path";
 * 3. a full-page screenshot, attached to the test. Artifacts only: no baseline is committed.
 *
 * The routes are the pages under `src/app/[locale]/(dashboard)` plus `select-clan`. There is no
 * account route in `src/app` (read at this commit), so none is walked. A `select-clan` visit by a
 * user with one membership selects it and lands on the dashboard; the landing URL is recorded as
 * an annotation, so the reading is of whatever the user actually sees.
 *
 * Dark is the colour-scheme media query alone (ADR-045), so emulating it is the whole setup.
 * The person the detail and edit pages need is made through the real form and soft-deleted at the
 * end, as `dashboard.auth.spec.ts` does.
 */

const { defaultBrowserType: _phoneBrowser, ...PIXEL_5 } = devices['Pixel 5']
const { defaultBrowserType: _desktopBrowser, ...DESKTOP } = devices['Desktop Chrome']

const VIEWPORTS = [
  { name: 'phone', use: PIXEL_5 },
  { name: 'desktop', use: DESKTOP },
] as const
const THEMES = ['light', 'dark'] as const

/** `messages/vi.json`'s top-level namespaces, which is what a missing key's path starts with. */
const NAMESPACES = Object.keys(
  JSON.parse(readFileSync(path.join(__dirname, '../../messages/vi.json'), 'utf8')),
)
const MESSAGE_KEY = new RegExp(
  `(?<![\\w./-])(?:${NAMESPACES.join('|')})\\.[a-z][a-z0-9_]*(?:\\.[a-z0-9_]+)*(?![\\w@-])`,
  'g',
)

/** `messages/vi.json`, `member_form.full_name`, `member_form.save_success`, `member_form.continue_label`. */
const FULL_NAME = 'Họ và tên'
const SAVED = 'Đã lưu thay đổi.'
const CONTINUE = 'Tiếp tục'

interface Route {
  readonly name: string
  readonly path: (personId: string) => string
}

const ROUTES: readonly Route[] = [
  { name: 'dashboard', path: () => '/vi/dashboard' },
  { name: 'members-list', path: () => '/vi/members' },
  { name: 'member-detail', path: (id) => `/vi/members/${id}` },
  { name: 'member-new', path: () => '/vi/members/new' },
  { name: 'member-edit', path: (id) => `/vi/members/${id}/edit` },
  { name: 'tree', path: () => '/vi/tree' },
  { name: 'events', path: () => '/vi/events' },
  { name: 'documents', path: () => '/vi/documents' },
  { name: 'admin-users', path: () => '/vi/admin/users' },
  { name: 'admin-clan', path: () => '/vi/admin/clan' },
  { name: 'select-clan', path: () => '/vi/select-clan' },
]

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle')
  // Skeletons and client queries resolve after the network goes quiet.
  await page.waitForTimeout(1_000)
}

async function visibleMessageKeys(page: Page): Promise<string[]> {
  const text = await page.evaluate(() => document.body.innerText)
  return [...new Set(text.match(MESSAGE_KEY) ?? [])]
}

let personId = ''
let clanId = ''

async function createPerson(browser: Browser): Promise<void> {
  const context = await browser.newContext({
    ...DESKTOP,
    baseURL: AUTH_BASE_URL,
    storageState: SEEDED_USERS.admin.storageState,
  })
  const page = await context.newPage()
  try {
    await page.goto('/vi/members/new')
    await page.getByLabel(FULL_NAME).fill(`Người đi dạo màn hình ${Date.now()}`)
    await page.getByRole('button', { name: 'Lưu' }).click()
    await expect(page.getByText(SAVED)).toBeVisible()
    await page.getByRole('button', { name: CONTINUE }).click()
    await expect(page).toHaveURL(/\/vi\/members\/[0-9a-f-]{36}$/)
    personId = new URL(page.url()).pathname.split('/').pop()!
    clanId = (await context.cookies()).find((c) => c.name === 'current_clan_id')?.value ?? ''
  } finally {
    await context.close()
  }
}

async function deletePerson(browser: Browser): Promise<void> {
  if (personId === '') return
  const context = await browser.newContext({
    baseURL: AUTH_BASE_URL,
    storageState: SEEDED_USERS.admin.storageState,
  })
  try {
    const page = await context.newPage()
    await page.goto('/vi/dashboard')
    const token = await browserAccessToken(context)
    const removed = await page.request.delete(
      `${authStackInputs().apiOrigin}/api/v1/persons/${personId}`,
      { headers: { Authorization: `Bearer ${token}`, 'X-Current-Clan-Id': clanId } },
    )
    expect(removed.status()).toBe(200)
  } finally {
    await context.close()
  }
}

// One worker, in order: the person is made once and removed once.
test.describe.configure({ mode: 'serial' })

test.beforeAll(async ({ browser }) => {
  test.setTimeout(90_000)
  await createPerson(browser)
})

test.afterAll(async ({ browser }) => {
  await deletePerson(browser)
})

for (const viewport of VIEWPORTS) {
  for (const theme of THEMES) {
    test.describe(`screen walk, ${viewport.name}, ${theme}`, () => {
      test.use({
        ...viewport.use,
        colorScheme: theme,
        storageState: SEEDED_USERS.admin.storageState,
      })

      for (const route of ROUTES) {
        test(`${route.name}: no overflow, no message key, screenshot`, async ({ page }, info) => {
          test.setTimeout(60_000)
          await page.goto(route.path(personId))
          await settle(page)
          info.annotations.push({ type: 'landed', description: new URL(page.url()).pathname })

          await info.attach(`${route.name}-${viewport.name}-${theme}`, {
            body: await page.screenshot({ fullPage: true }),
            contentType: 'image/png',
          })

          const { scrollWidth, clientWidth } = await page.evaluate(() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
          }))
          expect(scrollWidth, 'document scrollWidth against clientWidth').toBeLessThanOrEqual(
            clientWidth,
          )
          expect(await visibleMessageKeys(page), 'visible untranslated message keys').toEqual([])
        })
      }
    })
  }
}
