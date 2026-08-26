import { expect, test } from '@playwright/test'
import { BASE_URL } from '../../playwright.config'
import { SEEDED_USERS } from './fixtures'

/**
 * Seed S-070. The first authenticated screen this repository has ever read in a browser.
 *
 * **Why `/vi/backoffice/dashboard`.** Its layout is one line of gate —
 * `await requireRole(['admin', 'super_admin'], locale)`
 * (`src/app/[locale]/backoffice/layout.tsx:27`) — which is `requireServerRole`, the function
 * S-070 names in its Sources as the reason nothing was reachable. The screen is also the one
 * **ADR-046 is about**: `BackofficeSidebar`'s aside moved off a hand-built `bg-gray-950` onto
 * the `muted` token, and the `FR` mark kept `primary` on it. ADR-046 recorded contrast ratios
 * computed from the stylesheet and says in its own text that S-039 could not read the rail in
 * a browser. These cases read it.
 *
 * **Why not `/vi/members`, which four seeds actually wanted.** It was the first choice and it
 * was withdrawn on evidence. `members` is inside the `(dashboard)` group, whose layout runs
 * away: 2613 mount-effect re-runs and 18174 `GET /auth/me` calls in seven seconds, measured
 * 2026-08-26. A suite cannot take a stable reading on a screen that is re-rendering
 * thousands of times a second, and the loop is in `useAuth` and its store — legacy auth code
 * S-070 must not redesign. `web/CLAUDE.md` carries the measurement and the "how to add the
 * next one" recipe; the loop needs its own seed.
 *
 * **Every case reads an outcome the markup alone cannot produce.** The role pair is the
 * clearest: one URL, one build, two sessions, and the difference is a claim in a token a
 * real GoTrue signed.
 */

/** Tokens read from `src/app/globals.css`. Light value first, then the dark override. */
const TOKEN = {
  /** `--color-foreground`: `#1a1a1a` / `#f1ebde`. */
  foreground: { light: 'rgb(26, 26, 26)', dark: 'rgb(241, 235, 222)' },
  /** `--color-muted`, the aside's ground since ADR-046: `#f3f4f6` / `#24221a`. */
  muted: { light: 'rgb(243, 244, 246)', dark: 'rgb(36, 34, 26)' },
  /** `--color-primary`, the `FR` mark ADR-046 kept on that ground: `#3e5c38` / `#a3c398`. */
  primary: { light: 'rgb(62, 92, 56)', dark: 'rgb(163, 195, 152)' },
}

const BACKOFFICE_PATH = '/vi/backoffice/dashboard'

/** `messages/vi.json`, `Backoffice.dashboard_title`. */
const DASHBOARD_TITLE = 'Bảng điều khiển'
/** `messages/vi.json`, the four `Backoffice.nav_*` keys, in `NAV_ITEMS` order. */
const RAIL_LABELS = ['Tổng quan', 'Thành viên', 'Dòng họ', 'Cây gia phả']

test.describe('the backoffice dashboard, as an admin', () => {
  test.use({ storageState: SEEDED_USERS.admin.storageState })

  test('renders behind requireServerRole, with its rail', async ({ page }) => {
    const response = await page.goto(BACKOFFICE_PATH)

    expect(response?.status()).toBeLessThan(400)
    await expect(page).toHaveURL(new RegExp(`${BACKOFFICE_PATH}$`))
    await expect(page.locator('main h1')).toHaveText(DASHBOARD_TITLE)

    // The rail S-039 could not read. Located by accessible name, so this also fails if an
    // icon-only regression leaves a link with no name for a screen reader to announce.
    for (const label of RAIL_LABELS) {
      await expect(page.locator('aside').getByRole('link', { name: label })).toBeVisible()
    }
    await expect(page.locator('aside').getByRole('button')).toHaveAccessibleName(/\S/)
  })

  test('paints its tokens under both colour schemes', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' })
    await page.goto(BACKOFFICE_PATH)

    const heading = page.locator('main h1')
    const rail = page.locator('aside')
    // The `FR` mark: `text-primary` on the rail's `muted` ground, the exact pair ADR-046
    // decided. Its own numbers came from reading `globals.css`; this reads the engine.
    const mark = rail.getByText('FR', { exact: true })

    await expect(heading).toHaveCSS('color', TOKEN.foreground.light)
    await expect(rail).toHaveCSS('background-color', TOKEN.muted.light)
    await expect(mark).toHaveCSS('color', TOKEN.primary.light)

    // No reload. A colour-scheme change re-evaluates the media query in place, and ADR-045
    // made the media query the only mechanism — there is no class and no attribute to set —
    // so re-reading the same live elements is the honest test of the flip. It also keeps this
    // case to one page load, which matters: `/api/v1/auth/*` is limited to 20 requests per
    // 60 seconds (`backend/app/main.py:221-226`) and one load of this screen spends several.
    await page.emulateMedia({ colorScheme: 'dark' })

    // All three, on purpose. A ground that flips while an ink does not is the defect S-006
    // and S-038 were opened for, and asserting only the background would pass over it.
    await expect(heading).toHaveCSS('color', TOKEN.foreground.dark)
    await expect(rail).toHaveCSS('background-color', TOKEN.muted.dark)
    await expect(mark).toHaveCSS('color', TOKEN.primary.dark)

    // ADR-045's other half: the flip needs no marker on the document element.
    const marker = await page.evaluate(() => ({
      classes: document.documentElement.className,
      theme: document.documentElement.getAttribute('data-theme'),
    }))
    expect(marker.classes).not.toContain('dark')
    expect(marker.theme).toBeNull()
  })

  test.describe('at 320dp and 200% text scale', () => {
    // T-04, design spec § 5. Doubling the root font size is how rem-based type reacts to
    // browser text zoom, which Playwright cannot set directly; `e2e/text-scale.spec.ts` uses
    // the same lever and explains why the style goes in a tag rather than on `<html>`.
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 640 })
      await page.goto(BACKOFFICE_PATH)
      await page.addStyleTag({ content: ':root { font-size: 32px; }' })
      await page.evaluate(() => document.fonts.ready)
    })

    test('the page reports no horizontal scroll, which here proves almost nothing', async ({
      page,
    }) => {
      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))

      // Kept, because `e2e/text-scale.spec.ts` asks exactly this of the two public pages and
      // a reader will look for it here. **Do not read it as "the screen is usable."** It
      // passes on this screen while every pixel of content sits outside the viewport — see
      // the case below for the measurement. `.claude/rules/seeds.md`'s S-001 instance is the
      // same shape: a reading whose passing and failing values are indistinguishable.
      expect(scrollWidth).toBe(clientWidth)
    })

    /**
     * **A real, open T-04 defect, pinned rather than papered over.** Measured 2026-08-26 at
     * 320×640 with `:root { font-size: 32px }`, on this screen:
     *
     * ```
     * aside     x=0    width=480     // `w-60` is 15rem, 480px at a 32px root
     * main      x=480  width=0       // `ml-60` is another 480px, and flex-1 collapses
     * main h1   x=544  width=0
     * documentElement scrollWidth 320 === clientWidth 320, overflow-x: visible
     * ```
     *
     * The content column is pushed entirely off a 320px viewport and squeezed to zero width,
     * and because zero-width content cannot be scrolled to, the page still reports no
     * horizontal overflow. `src/app/[locale]/backoffice/layout.tsx:31-32` pairs a `fixed w-60`
     * rail with `ml-60` on `main`, and neither has a small-screen branch.
     *
     * `test.fail()` rather than a deleted case or an inverted assertion, following
     * `e2e/smoke.spec.ts`'s `lang` precedent: a `test.skip` would let a fix land unnoticed and
     * the coverage never come back, while an assertion that the heading *is* off-screen would
     * lock the bug in. This turns **red** the moment someone gives the rail a responsive
     * branch, which is the reminder to delete this comment and the `.fail`.
     *
     * Fixing it is out of S-070's scope — the seed says "any new screen" and "changing what
     * any route requires" are excluded, and a responsive backoffice rail is a design decision
     * ADR-046 did not make. It needs its own seed.
     */
    test.fail(
      'the content column is off-screen entirely, so the heading is not inside the viewport',
      async ({ page }) => {
        const clientWidth = await page.evaluate(() => document.documentElement.clientWidth)
        const box = await page.locator('main h1').boundingBox()

        expect(box).not.toBeNull()
        expect(box!.x).toBeGreaterThanOrEqual(0)
        expect(box!.x + box!.width).toBeLessThanOrEqual(clientWidth)
      },
    )
  })
})

/**
 * The role gate, read as HTTP rather than as a rendered page.
 *
 * `page.request` shares the browser context's cookies and runs no page JavaScript, so these
 * two cases cost nothing in renders and can be trusted not to depend on any client effect.
 * `maxRedirects: 0` is the point: the **Location** is the reading, and the two Locations
 * differ, which is what makes this a control rather than a restatement.
 */
test.describe('the role gate answers two different refusals', () => {
  test.describe('to a viewer, who has a real session', () => {
    test.use({ storageState: SEEDED_USERS.viewer.storageState })

    test('requireServerRole sends them to the dashboard', async ({ page }) => {
      const response = await page.request.get(BACKOFFICE_PATH, { maxRedirects: 0 })

      expect(response.status()).toBe(307)
      expect(response.headers()['location']).toMatch(/\/vi\/dashboard$/)
    })
  })

  test.describe('to nobody at all', () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test('middleware sends them to login instead', async ({ page }) => {
      const response = await page.request.get(BACKOFFICE_PATH, { maxRedirects: 0 })

      // A different status and a different Location from the viewer's refusal above. If both
      // readings were `307 → /vi/login`, the viewer case would be proving only that the
      // request had no session, which is the failure mode `.claude/rules/seeds.md` records
      // for S-001: a control whose passing and failing readings are the same value.
      expect(response.status()).toBe(307)
      expect(response.headers()['location']).toMatch(/\/vi\/login$/)
    })
  })
})

/**
 * The fencing measurement, and the reason it is a test rather than a paragraph.
 *
 * The harness's claim is that what it holds is worthless anywhere else. Cookies written by
 * `@supabase/ssr` are named for the project they came from — `sb-<ref>-auth-token` — and the
 * token inside is signed by that stack's key. So the captured state is replayed against the
 * *hermetic* dev server on :3100, which S-041 points at
 * `https://e2e-fake-project.example.supabase.co`: a different project, a different cookie
 * name, a different key.
 *
 * **What this proves and what it does not.** It proves a session captured from one Supabase
 * project does not carry into a build pointed at another. It does not prove that middleware
 * verifies a signature — it does not: `supabase.auth.getSession()` reads the cookie. A
 * token's signature is checked by the backend's JWKS flow when the token is used
 * (`backend/app/core/security.py`), which is a separate guarantee and belongs to S-072.
 */
test.describe('the captured session does not travel', () => {
  test.use({ storageState: SEEDED_USERS.admin.storageState })

  test('replayed against a build pointed at another Supabase project, it is nobody', async ({
    page,
  }) => {
    const response = await page.request.get(`${BASE_URL}${BACKOFFICE_PATH}`, { maxRedirects: 0 })

    expect(response.status()).toBe(307)
    expect(response.headers()['location']).toMatch(/\/vi\/login$/)
  })
})
