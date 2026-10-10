import { expect, test, type Page } from '@playwright/test'
import { BASE_URL } from '../../playwright.config'
import { SEEDED_USERS } from './fixtures'

/**
 * the authenticated e2e harness. The first authenticated screen this repository has ever read in a browser.
 *
 * **Why `/vi/backoffice/dashboard`.** Its layout is one line of gate. It was
 * `await requireRole(['admin', 'super_admin'], locale)`, which is `requireServerRole`, the
 * function the authenticated e2e harness names in its Sources as the reason nothing was
 * reachable. Since #186 it is `await guardClanRoute(locale, 'viewPendingUsers')`
 * (`src/app/[locale]/backoffice/layout.tsx`). The screen is also the one
 * **ADR-046 is about**: `BackofficeSidebar`'s aside moved off a hand-built `bg-gray-950` onto
 * the `muted` token, and the `FR` mark kept `primary` on it. ADR-046 recorded contrast ratios
 * computed from the stylesheet and says in its own text that ADR-046 could not read the rail in
 * a browser. These cases read it.
 *
 * **Why not `/vi/members`, which four seeds actually wanted.** It was the first choice and it
 * was withdrawn on evidence. `members` is inside the `(dashboard)` group, whose layout ran
 * away: 2613 mount-effect re-runs and 18174 `GET /auth/me` calls in seven seconds, measured
 * 2026-08-26. A suite cannot take a stable reading on a screen that is re-rendering
 * thousands of times a second. #183 removed the loop by holding the session in one query, and
 * `dashboard.auth.spec.ts` now reads `/vi/members`.
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
/** The same route under `en`, the locale whose words are widest in T-04's boxes (#236). */
const BACKOFFICE_PATH_EN = '/en/backoffice/dashboard'

/** `messages/vi.json`, `Backoffice.dashboard_title`. */
const DASHBOARD_TITLE = 'Bảng điều khiển'
/** `messages/en.json`, `Backoffice.dashboard_title`. */
const DASHBOARD_TITLE_EN = 'Backoffice Dashboard'
/** `messages/vi.json`, the four `Backoffice.nav_*` keys, in `NAV_ITEMS` order. */
const RAIL_LABELS = ['Tổng quan', 'Thành viên', 'Dòng họ', 'Cây gia phả']
/** `messages/vi.json`, `Backoffice.menu_open`: the top bar's menu button below `lg`. */
const MENU_OPEN = 'Mở menu điều hướng'
/** `messages/vi.json`, `common.close`: the drawer's close button. */
const CLOSE = 'Đóng'
/** T-04's viewport: 320 px wide, and tall enough to be a phone. */
const NARROW = { width: 320, height: 640 }
/**
 * #212: the widths the T-04 case resizes through, in place. T-04 names only 320, but the
 * dashboard's grids broke from 640 up, and worst at 1024, where the `lg` rail at a 32px root
 * leaves `main` 496 px. 375 is a phone, and the 100% reading names it.
 */
const WIDTHS = [320, 375, 640, 768, 1024, 1280, 1440]
/** The one width where the 100% stat text may stack under its icon, as it did before #212. */
const STACK_ALLOWED_AT = 1024

/**
 * One reading of the dashboard's boxes, run in the page by `page.evaluate`, so it closes over
 * nothing. The stat grid is `main`'s one list. The quick-action grid is the approvals card's
 * parent, found through the one link that carries a badge.
 */
function readDashboard() {
  const edges = (r: DOMRect) => ({ left: r.left, right: r.right, top: r.top, bottom: r.bottom })
  const card = (el: Element) => ({
    text: el.querySelector('h3, p')?.textContent ?? '',
    box: edges(el.getBoundingClientRect()),
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  })
  const grid = (el: Element) => ({
    box: edges(el.getBoundingClientRect()),
    cards: [...el.children].map((child) => edges(child.getBoundingClientRect())),
  })
  const main = document.querySelector('main')!
  const stats = main.querySelector('ul')!
  const action = main.querySelector('a[href$="/backoffice/approvals"]')!
  const actions = action.parentElement!
  const title = action.querySelector('h3')!
  const range = document.createRange()
  range.selectNodeContents(title)
  return {
    page: {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    },
    stats: [...stats.querySelectorAll(':scope > li')].map((li) => ({
      ...card(li),
      lines: li.querySelectorAll('p').length,
      icon: edges(li.querySelector('svg')!.parentElement!.getBoundingClientRect()),
      column: edges(li.querySelector('p')!.parentElement!.getBoundingClientRect()),
    })),
    actions: [...actions.children].map(card),
    statGrid: grid(stats),
    actionGrid: grid(actions),
    lines: [...main.querySelectorAll('h1, h2, h3, p')].map((line) => ({
      text: line.textContent,
      clientWidth: line.clientWidth,
      scrollWidth: line.scrollWidth,
    })),
    title: { text: title.textContent, box: edges(title.getBoundingClientRect()) },
    inked: [...range.getClientRects()].map(edges),
    badges: [...action.querySelectorAll('span')].map((b) => edges(b.getBoundingClientRect())),
  }
}

test.describe('the backoffice dashboard, as an admin', () => {
  test.use({ storageState: SEEDED_USERS.admin.storageState })

  test('renders behind the server guard, with its rail', async ({ page }) => {
    const response = await page.goto(BACKOFFICE_PATH)

    expect(response?.status()).toBeLessThan(400)
    await expect(page).toHaveURL(new RegExp(`${BACKOFFICE_PATH}$`))
    await expect(page.locator('main h1')).toHaveText(DASHBOARD_TITLE)

    // The rail ADR-046 could not read. Located by accessible name, so this also fails if an
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
    // 60 seconds by default (`RATE_LIMIT_AUTH_MAX_REQUESTS`; the harness's backend sets 1000,
    // #226) and one load of this screen spends several.
    await page.emulateMedia({ colorScheme: 'dark' })

    // All three, on purpose. A ground that flips while an ink does not is the defect the dark-palette change
    // and the palette sweep were opened for, and asserting only the background would pass over it.
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
    // A helper rather than a `beforeEach`, because the cases do not read one locale: each
    // names its path, and each still spends one navigation. It returns the style tag, so a case
    // can remove it and read the same load at 100%.
    async function openAtTextScale(page: Page, path: string) {
      await page.setViewportSize(NARROW)
      await page.goto(path)
      const scale = await page.addStyleTag({ content: ':root { font-size: 32px; }' })
      await page.evaluate(() => document.fonts.ready)
      await settle(page)
      return scale
    }

    // Let every transition a change started land. The quick-action cards carry
    // `transition-all`, so when the scale changes their `p-5` animates between 20 and 40 px,
    // and a box read before it lands is one the page never settles on (#175: the approvals
    // title read x 91 to 229 mid-transition, where its padding lands it at 105 to 215). A
    // resize is awaited the same way (#212). A cancelled transition has nothing to wait for.
    async function settle(page: Page) {
      await page.evaluate(() =>
        Promise.all(
          document
            .getAnimations()
            .filter((animation) => animation instanceof CSSTransition)
            .map((animation) => animation.finished.catch(() => undefined)),
        ),
      )
    }

    /** Resize in place. `setViewportSize` does not navigate, so it costs no request. */
    async function readAt(page: Page, width: number) {
      await page.setViewportSize({ width, height: NARROW.height })
      await settle(page)
      return page.evaluate(readDashboard)
    }

    /**
     * T-04's three clauses, as far as this page can break them: no horizontal scroll, no clipped
     * line of text in `main`, and no badge on its title, the one element that was ever placed
     * over another. One case and one navigation, because the page-level scroll reading already
     * paid for this load, and `web/CLAUDE.md` ("Budget the requests") keeps a case to one.
     *
     * **#175, the two defects the scroll reading passed over.** Measured 2026-10-04 at 320×640
     * with `:root { font-size: 32px }`, before the fix: the icon box and `gap-4` filled the
     * stat card, so its text column was 0 px wide and the card's `overflow-hidden` hid every
     * value, `248`, `7`, `134` and `73%` at `clientWidth` 0 against `scrollWidth` 85, 25, 77
     * and 96. And the approvals badge, `absolute top-4 right-4`, sat on its card's title: badge
     * x 183 to 223, title x 105 to 215, on the same lines.
     *
     * The fix, read the same way after it: the stat text wraps under its icon, every line of
     * every card fits its box at 174 px, and the badge takes a line of its own above a title
     * 174 px wide. The negative controls, each planted and reverted on 2026-10-04: the old stat
     * row and `p-8` together read the four values at `clientWidth` 0 against 85, 25, 77 and 96;
     * the old row alone reads every label and value at 54; `p-8` alone clips `Approvals`,
     * `Documents` and `Completeness` at 110 against 111, 130 and 164; and the absolute badge
     * reads x 215 to 255, y 2651 to 2691, across a title box from x 73 to 247, y 2659 to 2739.
     *
     * **This case reads `en` (#236), the one locale that fails under every control below.** The
     * labels those 2026-10-04 controls clipped were English literals under every locale. #197
     * translated them, so `/vi` rendered Vietnamese, whose widest card word is 79 px against
     * card boxes of 110 and more (its `h1`'s, `khiển`, is 125 in 256), and with `p-8` planted on
     * 2026-10-06 the case passed. `/en` costs
     * the same one navigation. Measured 2026-10-10 on `/en`: every stat and quick-action line
     * fits its 174 px box and the `h1` its 256. The negative controls, each planted and reverted
     * that day: `p-8` in place of `px-4 py-8 sm:px-8` clips `Documents`, `Tree Completeness`,
     * `Add member` and `Review approvals` at 110 against 131, 164, 115 and 133, both long
     * descriptions at 110 against 145 and 146, and spills a stat card, 204 against 190. Spec
     * § 2.4's `space-5` gutter, `px-5`, clips `Tree Completeness` at 158 against 164. And the
     * badge kept beside the title, the row without `flex-wrap-reverse`, clips `Review approvals`
     * at 110 against 133: `approvals` inks to x 206 past a title box ending at 183, beside a
     * badge from x 207. `.claude/rules/tailwind.md` § 7 has the table.
     *
     * **Reading `en` found one more clipped line, the `h1`.** `Dashboard` is 258 px in the 256 px
     * column, so with only the path moved to `en` the case read `Backoffice Dashboard` at
     * `clientWidth` 256 against `scrollWidth` 258. The `h1` carries `wrap-break-word` for it, so
     * it reads `Dashboar` then `d`, and with that removed the case fails on the same reading.
     *
     * **#212, every width past T-04's 320.** The grids' column counts were viewport breakpoints,
     * which do not grow with text. At 1024 px and 200%, where the `lg` rail leaves `main` 496 px,
     * every stat line read `clientWidth` 0 and every quick-action line 19, and the quick actions
     * scrolled the page, 1044 against 1024. The case now resizes
     * in place through `WIDTHS` and asks every clause at each, then drops the style tag and asks
     * two more at 100%: the stat text beside its icon, and no empty track beside a one-row grid.
     * Resizing and dropping the tag do not navigate, so this is still one load. The negative
     * controls, each planted and reverted on 2026-10-10, are in `.claude/rules/tailwind.md` § 7:
     * each old grid, the minimums without `min(…, 100%)`, `auto-fill` for `auto-fit`, a `10rem`
     * stat minimum, and stat cards pulled up into each other each fail a reading here.
     */
    test('the page passes T-04: no scroll, no clipped text, no badge on a title', async ({
      page,
    }) => {
      const scaleTag = await openAtTextScale(page, BACKOFFICE_PATH_EN)
      await expect(page.locator('main h1')).toHaveText(DASHBOARD_TITLE_EN)

      type Edges = ReturnType<typeof readDashboard>['badges'][number]
      const meets = (a: Edges, b: Edges) =>
        a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top

      // #212: T-04's clauses at every width, resized in place on the one load.
      for (const width of WIDTHS) {
        const reading = await readAt(page, width)
        const at = `at ${width} px and 200% text`

        // Kept, because `e2e/text-scale.spec.ts` asks exactly this of the two public pages and
        // a reader will look for it here. **Do not read it as "the screen is usable."** It
        // passed on this screen while every pixel of content sat outside the viewport (#174,
        // measured below), and again while every stat value was clipped to nothing (#175, above).
        // `.claude/rules/testing.md`'s token-fix instance is the same shape: a reading whose
        // passing and failing values are indistinguishable. Here it does read something: the
        // grid with no clamp to its container fails only this line (#212).
        expect.soft(reading.page.scrollWidth, at).toBe(reading.page.clientWidth)

        // 1. Every heading and paragraph in `main` shows whole: each stat card's label, value and
        //    trend line, and each quick action's title and description. A line with no width is
        //    the stat defect, and a line wider than its box is clipped by `truncate` or by the
        //    card. The card counts first, so a selector that finds no card cannot pass vacuously.
        expect(reading.stats, at).toHaveLength(4)
        expect(reading.actions, at).toHaveLength(3)
        for (const card of reading.stats) expect(card.lines, at).toBeGreaterThanOrEqual(2)
        const clipped = reading.lines.filter(
          (line) => line.clientWidth === 0 || line.scrollWidth > line.clientWidth,
        )
        expect.soft(clipped, at).toEqual([])
        const cards = [...reading.stats, ...reading.actions]
        const spilled = cards
          .filter((card) => card.scrollWidth > card.clientWidth)
          .map(({ text, scrollWidth, clientWidth }) => ({ text, clientWidth, scrollWidth }))
        expect.soft(spilled, at).toEqual([])

        // 2. No card overlaps another, across both grids.
        const overlapping = cards.flatMap((a, i) =>
          cards.slice(i + 1).flatMap((b) => (meets(a.box, b.box) ? [[a.text, b.text]] : [])),
        )
        expect.soft(overlapping, at).toEqual([])

        // 3. The badge clears its card's title: the title's box, and every line of the title as
        //    inked, which can spill past that box.
        expect(reading.badges, at).toHaveLength(1)
        const [badge] = reading.badges
        expect(reading.inked.length, at).toBeGreaterThan(0)
        expect
          .soft(
            meets(badge, reading.title.box),
            `${at}: ${JSON.stringify({ badge, ...reading.title })}`,
          )
          .toBe(false)
        expect
          .soft(
            reading.inked.filter((line) => meets(badge, line)),
            at,
          )
          .toEqual([])
      }

      // #212: the same load at 100% text, so the fix for 200% cannot cost the default size.
      await scaleTag.evaluate((tag) => tag.parentNode!.removeChild(tag))
      await settle(page)
      let oneRow = 0
      for (const width of WIDTHS) {
        const reading = await readAt(page, width)
        const at = `at ${width} px and 100% text`

        // 4. Each stat card's text sits beside its icon: the text column starts above the icon
        //    box's bottom. #175 let it stack at 1024 px, and it still may there.
        if (width !== STACK_ALLOWED_AT) {
          const stacked = reading.stats.filter((card) => card.column.top >= card.icon.bottom)
          expect
            .soft(
              stacked.map((card) => card.text),
              at,
            )
            .toEqual([])
        }

        // 5. A grid whose cards all sit on one row spans that row: no empty column track
        //    beside them. Read off the cards' boxes against the grid's, so it is the space a
        //    reader sees and not the template that leaves it.
        for (const grid of [reading.statGrid, reading.actionGrid]) {
          if (new Set(grid.cards.map((card) => Math.round(card.top))).size !== 1) continue
          oneRow += 1
          expect
            .soft(
              {
                emptyLeft: Math.round(Math.min(...grid.cards.map((c) => c.left)) - grid.box.left),
                emptyRight: Math.round(
                  grid.box.right - Math.max(...grid.cards.map((c) => c.right)),
                ),
              },
              `${at}, ${grid.cards.length} cards on one row`,
            )
            .toEqual({ emptyLeft: 0, emptyRight: 0 })
        }
      }
      // Clause 5 is read only where a row holds every card, so it must have been read somewhere.
      expect(oneRow).toBeGreaterThan(0)
    })

    /**
     * **#174, the defect this describe used to pin with `test.fail()`.** Measured 2026-08-26 at
     * 320×640 with `:root { font-size: 32px }`, before the fix:
     *
     * ```
     * aside     x=0    width=480     // `w-60` is 15rem, 480px at a 32px root
     * main      x=480  width=0       // `ml-60` is another 480px, and flex-1 collapses
     * main h1   x=544  width=0
     * documentElement scrollWidth 320 === clientWidth 320, overflow-x: visible
     * ```
     *
     * Below `lg` the rail is now a drawer behind a top bar, so these two cases read what the
     * fix is for rather than what the page reports. **They read `/vi`**, where every reading and
     * control below was taken; #236 moved only the case above to `en`. Two cases, one navigation
     * each, per `web/CLAUDE.md`'s "Budget the requests". The negative controls, each planted and
     * reverted on 2026-10-04, are in the #174 pull request. Restoring `fixed w-60` + `ml-60`
     * reads `main` width 0. An icon-only rail reads width 176 and `scrollWidth` 190. The rail
     * stacked above `main` puts the heading's bottom at 968. Removing the `<wbr>` overflows the
     * top bar, 325 against 320. Putting the drawer's brand and close button back on one line inks
     * the wordmark across the button, and doing that with the `<wbr>` and `min-w-0` gone too, the
     * prototype's arrangement, overflows the drawer, 341 against 272.
     */
    test('the content column fills the screen, and its heading is in the first viewport', async ({
      page,
    }) => {
      await openAtTextScale(page, BACKOFFICE_PATH)
      await expect(page.locator('main h1')).toHaveText(DASHBOARD_TITLE)

      const reading = await page.evaluate(() => {
        const main = document.querySelector('main')!
        const box = main.getBoundingClientRect()
        const heading = main.querySelector('h1')!.getBoundingClientRect()
        const topBar = document.querySelector('header')!
        return {
          clientWidth: document.documentElement.clientWidth,
          topBar: { scrollWidth: topBar.scrollWidth, clientWidth: topBar.clientWidth },
          main: { width: box.width, scrollWidth: main.scrollWidth, clientWidth: main.clientWidth },
          heading: { x: heading.x, y: heading.y, right: heading.right, bottom: heading.bottom },
        }
      })

      // Soft, so a planted failure reports every reading it breaks rather than the first.
      // 1. The column is the whole screen, not the 0 px it was.
      expect.soft(reading.clientWidth).toBe(NARROW.width)
      expect.soft(reading.main.width).toBe(reading.clientWidth)
      // 2. Nothing overflows inside it. The page-level scroll case above cannot see this.
      expect.soft(reading.main.scrollWidth).toBeLessThanOrEqual(reading.main.clientWidth)
      // 3. The heading is inside the first viewport, so the top bar costs no more than it must.
      expect.soft(reading.heading.x).toBeGreaterThanOrEqual(0)
      expect.soft(reading.heading.right).toBeLessThanOrEqual(NARROW.width)
      expect.soft(reading.heading.y).toBeGreaterThanOrEqual(0)
      expect.soft(reading.heading.bottom).toBeLessThanOrEqual(NARROW.height)
      // The top bar holds its brand. Unbroken, the wordmark ran 5px past it.
      expect.soft(reading.topBar.scrollWidth).toBeLessThanOrEqual(reading.topBar.clientWidth)
    })

    test('the rail is one tap away, in a drawer that fits', async ({ page }) => {
      // `/vi`, like the case above: the drawer's readings and #174's controls were taken there.
      await openAtTextScale(page, BACKOFFICE_PATH)
      // Let the page's own requests finish before counting what the tap costs.
      await page.waitForLoadState('networkidle')
      const hydrations: string[] = []
      page.on('request', (request) => {
        if (/\/api\/v1\/(auth\/me|me\/clans)$/.test(new URL(request.url()).pathname)) {
          hydrations.push(request.url())
        }
      })

      await page.getByRole('button', { name: MENU_OPEN }).click()
      const drawer = page.getByRole('dialog')

      // 4. The four links, by accessible name, and the drawer holds them without overflowing.
      for (const label of RAIL_LABELS) {
        await expect(drawer.getByRole('link', { name: label })).toBeVisible()
      }
      const { scrollWidth, clientWidth } = await drawer.evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      }))
      expect(scrollWidth).toBe(clientWidth)

      // No overlap, which the width above cannot see: the brand's text may spill out of its own
      // box and still sit inside the drawer. Read where each line of it is inked, and require
      // every line to clear the close button.
      const close = (await drawer.getByRole('button', { name: CLOSE }).boundingBox())!
      const inked = await drawer.evaluate((el) =>
        [...el.querySelectorAll('p')].flatMap((p) => {
          const range = document.createRange()
          range.selectNodeContents(p)
          return [...range.getClientRects()].map((r) => ({
            text: p.textContent,
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
          }))
        }),
      )
      expect(inked.length).toBeGreaterThan(0)
      const overlapping = inked.filter(
        (r) =>
          r.left < close.x + close.width &&
          r.right > close.x &&
          r.top < close.y + close.height &&
          r.bottom > close.y,
      )
      expect(overlapping).toEqual([])

      // Opening the drawer mounts a second copy of the rail body. It must not read the session
      // again: the rail's sign-out is an action, and an action sends nothing until it is used.
      await page.waitForLoadState('networkidle')
      expect(hydrations).toEqual([])

      // A tap on the scrim closes it: a navigation drawer has nothing to lose on dismiss.
      await page.mouse.click(NARROW.width - 8, NARROW.height / 2)
      await expect(drawer).toBeHidden()
    })
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

    test('the guard sends them to the dashboard, for want of viewPendingUsers', async ({
      page,
    }) => {
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
      // request had no session, which is the failure mode `.claude/rules/testing.md` records
      // for the token fix: a control whose passing and failing readings are the same value.
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
 * *hermetic* dev server at `BASE_URL`, which the hermetic e2e config points at
 * `https://e2e-fake-project.example.supabase.co`: a different project, a different cookie
 * name, a different key.
 *
 * **What this proves and what it does not.** It proves a session captured from one Supabase
 * project does not carry into a build pointed at another. It does not prove that middleware
 * verifies a signature — it does not: `supabase.auth.getSession()` reads the cookie. A
 * token's signature is checked by the backend's JWKS flow when the token is used
 * (`backend/app/core/security.py`), which is a separate guarantee and belongs to the local Supabase stack.
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
