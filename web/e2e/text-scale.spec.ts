import { expect, test } from '@playwright/test'

/**
 * T-04, the half of it no other suite can reach: at 320dp width and 200% text
 * scale, a screen must produce **no horizontal page scroll** (design spec § 5,
 * `T-04`). Type-check, lint and the component suite all pass over an overflowing
 * box, because jsdom has no layout engine. Only a real browser measures it.
 *
 * Doubling the root font size is how rem-based type reacts to browser text zoom,
 * which Playwright cannot set directly. `e2e/fonts.spec.ts` uses the same lever.
 *
 * Why the wordmark gets its own assertion: it was the only overflowing box on
 * either page when S-034 was opened (`h1` `clientWidth` 256, `scrollWidth` 350).
 * Asserting the page total alone would report "something overflows" and leave
 * the next reader to find out what.
 */

/** 320dp is the width `T-04` names. The height is arbitrary; only width is measured. */
const NARROW_VIEWPORT = { width: 320, height: 640 }

/** 200% of the 16px default root size. */
const DOUBLED_ROOT_FONT_SIZE = '32px'

/** The two routes reachable without a Supabase session. */
const PUBLIC_PAGES = ['/vi/login', '/vi/register']

async function loadAtDoubledTextScale(
  page: import('@playwright/test').Page,
  path: string,
): Promise<void> {
  await page.setViewportSize(NARROW_VIEWPORT)
  await page.goto(path)
  // Apply the scale through a stylesheet rather than an inline style on `<html>`.
  // `<html>` is React-owned, so writing `documentElement.style` before hydration
  // finishes raises a hydration attribute mismatch in the dev server log — noise
  // produced by the test itself, which a later reader would read as an app defect.
  await page.addStyleTag({ content: `:root { font-size: ${DOUBLED_ROOT_FONT_SIZE}; }` })
  // Plus Jakarta Sans is wider than the system fallback at this size, so a
  // reading taken before the face lands measures the wrong font.
  await page.evaluate(() => document.fonts.ready)
}

for (const path of PUBLIC_PAGES) {
  test.describe(`${path} at 320dp and 200% text scale`, () => {
    test.beforeEach(async ({ page }) => {
      await loadAtDoubledTextScale(page, path)
    })

    test('the page does not scroll horizontally', async ({ page }) => {
      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))

      expect(scrollWidth).toBe(clientWidth)
    })

    test('the wordmark fits its column and still reads as the product name', async ({ page }) => {
      const wordmark = page.locator('h1').first()

      await expect(wordmark).toBeVisible()

      // `<wbr>` inserts a break opportunity, not a character: the text content
      // stays one word, so this is also the assertion that the fix did not
      // change what a screen reader announces or what a copy-paste yields.
      // Read `textContent` rather than using `toHaveText`, which normalises
      // whitespace and so would pass over a stray space between the halves.
      expect(await wordmark.evaluate((el) => el.textContent)).toBe('FamilyRoots')

      const { scrollWidth, clientWidth } = await page.evaluate(() => {
        const heading = document.querySelector('h1')
        if (!heading) throw new Error('no h1 on the page')
        return { scrollWidth: heading.scrollWidth, clientWidth: heading.clientWidth }
      })

      expect(scrollWidth).toBeLessThanOrEqual(clientWidth)
    })
  })
}
