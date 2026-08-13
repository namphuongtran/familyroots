import { expect, test } from '@playwright/test'

/**
 * The assertion no other suite can make: that the mandated typefaces reach the
 * screen. Before S-002, `globals.css` named `'Inter'` and `'Playfair Display'`
 * literally while `next/font` served a generated family name, so the browser
 * silently fell back to a system face. Nothing in type-check, lint or the unit
 * suite can see that. Only a computed style in a real browser can.
 *
 * `next/font` generates the family name from the JavaScript constant it is
 * assigned to, and the casing follows that constant: reading `/vi/login` in
 * Chromium on 2026-08-13 gave `manrope, "manrope Fallback", system-ui,
 * sans-serif`. So these tests match case-insensitively on the readable part and
 * never on a hardcoded family string.
 */

/** Every Vietnamese tone mark and every modified vowel, plus đ and Đ. */
const FULL_DIACRITICS =
  'Nguyễn Trần Đỗ Phạm Hưng Việt — ạảãăắằẳẵặâấầẩẫậđêếềểễệôốồổỗộơớờởỡợưứừửữựỳỵỷỹý'

async function computedFontFamily(
  page: import('@playwright/test').Page,
  selector: string,
): Promise<string> {
  return page.evaluate((sel) => {
    const element = document.querySelector(sel)
    if (!element) throw new Error(`no element matched ${sel}`)
    return getComputedStyle(element).fontFamily
  }, selector)
}

test.describe('the mandated typefaces load and are applied', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/vi/login')
    // A face is only reported as loaded once something on the page uses it.
    await page.evaluate(() => document.fonts.ready)
  })

  test('body text renders in Manrope', async ({ page }) => {
    const family = await computedFontFamily(page, 'body')

    expect(family).toMatch(/manrope/i)
    expect(family).not.toMatch(/inter|playfair|noto/i)
  })

  test('a heading renders in Plus Jakarta Sans', async ({ page }) => {
    // The login page's h1 carries `font-serif`, which is the heading token.
    const family = await computedFontFamily(page, 'h1')

    expect(family).toMatch(/jakarta/i)
    expect(family).not.toMatch(/inter|playfair|noto/i)
  })

  test('a heading with no class inherits the heading face from the base rule', async ({ page }) => {
    // The utilities layer beats the base layer, so every heading that carries
    // `font-serif` would pass the test above even if the base rule named a dead
    // font. This pins the base rule itself, which is what an unstyled heading
    // gets.
    const family = await page.evaluate(() => {
      const heading = document.createElement('h2')
      heading.textContent = 'Gia phả'
      document.body.append(heading)
      return getComputedStyle(heading).fontFamily
    })

    expect(family).toMatch(/jakarta/i)
    expect(family).not.toMatch(/inter|playfair|noto/i)
  })

  test('both faces are loaded, not merely named', async ({ page }) => {
    // A literal family name, which is the defect S-002 fixed, leaves the computed
    // value looking plausible while no matching face exists. This is the part
    // that catches it: the browser reports a real, loaded face for each name.
    //
    // Check only the first family in the stack. `next/font` also registers a
    // metric-adjusted `... Fallback` face, that face is never used, and
    // `document.fonts.check` is false for any list holding an unloaded face.
    const state = await page.evaluate(() => {
      const firstFamily = (selector: string) =>
        getComputedStyle(document.querySelector(selector)!)
          .fontFamily.split(',')[0]
          .trim()
          .replace(/^["']|["']$/g, '')

      const report = (selector: string, weight: number) => {
        const family = firstFamily(selector)
        const face = [...document.fonts].find(
          (f) => f.family.replace(/^["']|["']$/g, '') === family,
        )
        return {
          available: document.fonts.check(`${weight} 16px "${family}"`),
          status: face?.status,
          // Both files are variable fonts. Without this range the browser would
          // render Manrope at its ExtraLight default instance.
          weightRange: face?.weight,
        }
      }

      return { body: report('body', 400), heading: report('h1', 700) }
    })

    expect(state).toEqual({
      body: { available: true, status: 'loaded', weightRange: '200 800' },
      heading: { available: true, status: 'loaded', weightRange: '200 800' },
    })
  })

  test('Vietnamese diacritics render in Manrope at 200% text scale', async ({ page }) => {
    // T-04. Doubling the root font size is how rem-based type reacts to browser
    // text zoom, which Playwright cannot set directly.
    const family = await page.evaluate((diacritics) => {
      document.documentElement.style.fontSize = '32px'
      const probe = document.createElement('p')
      probe.textContent = diacritics
      probe.id = 'diacritic-probe'
      document.body.prepend(probe)
      return getComputedStyle(probe).fontFamily
    }, FULL_DIACRITICS)

    expect(family).toMatch(/manrope/i)
    await expect(page.locator('#diacritic-probe')).toBeVisible()
  })
})
