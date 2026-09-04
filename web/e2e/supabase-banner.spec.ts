import { expect, test } from '@playwright/test'
import { BANNER_BASE_URL } from '../playwright.config'

/**
 * the banner spec, the half of `T-04` that the hermetic e2e config made invisible to every other spec in this file: with
 * both `NEXT_PUBLIC_SUPABASE_*` variables genuinely unset, `SupabaseSetupNotice.tsx` renders the
 * missing-Supabase banner, and at 320px width and 200% root font size the banner's own hint text
 * — which names both variables literally, so a developer who hits it knows what to set — used to
 * scroll the whole page sideways (measured 2026-08-22: page `scrollWidth` 569 vs `clientWidth`
 * 320, hint paragraph 504 vs 190; see `.claude/rules/tailwind.md` § 7).
 *
 * This spec talks to its own dev server on `BANNER_PORT`, not the shared `BASE_URL` every other
 * spec in this directory uses — see `playwright.config.ts`'s `NO_SUPABASE_ENV` webServer entry
 * for why one process can't serve both answers.
 */

/** 320dp is the width `T-04` names. The height is arbitrary; only width is measured. */
const NARROW_VIEWPORT = { width: 320, height: 640 }

/** 200% of the 16px default root size. Matches `text-scale.spec.ts`. */
const DOUBLED_ROOT_FONT_SIZE = '32px'

/** The two routes reachable without a Supabase session. */
const PUBLIC_PAGES = ['/vi/login', '/vi/register']

async function loadAtDoubledTextScale(
  page: import('@playwright/test').Page,
  path: string,
): Promise<void> {
  await page.setViewportSize(NARROW_VIEWPORT)
  await page.goto(`${BANNER_BASE_URL}${path}`)
  // Same reasoning as `text-scale.spec.ts`: writing `documentElement.style` directly, before
  // hydration finishes, raises a hydration attribute mismatch in the dev-server log — noise the
  // test itself would produce. A stylesheet avoids it.
  await page.addStyleTag({ content: `:root { font-size: ${DOUBLED_ROOT_FONT_SIZE}; }` })
  // Plus Jakarta Sans / Manrope are wider than the system fallback at this size, so a reading
  // taken before the face lands measures the wrong font.
  await page.evaluate(() => document.fonts.ready)
}

for (const path of PUBLIC_PAGES) {
  test.describe(`${path} at 320dp and 200% text scale, with no Supabase env`, () => {
    test.beforeEach(async ({ page }) => {
      await loadAtDoubledTextScale(page, path)
    })

    test('the missing-Supabase banner renders', async ({ page }) => {
      // A precondition, not the assertion this case exists for: if the banner did not render at
      // all, the page-scroll assertion below would pass for the wrong reason — there would be
      // nothing left to overflow, and the whole point of this spec (the hermetic e2e config's placeholders must not
      // leak into this one server) would be silently unverified.
      await expect(page.getByText('NEXT_PUBLIC_SUPABASE_URL')).toBeVisible()
    })

    test('the page does not scroll horizontally', async ({ page }) => {
      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))

      expect(scrollWidth).toBe(clientWidth)
    })

    test('the banner still names both missing variables', async ({ page }) => {
      // The fix must add break opportunities, not remove information. Read `textContent` rather
      // than relying on `toHaveText`'s whitespace normalisation, and require both full variable
      // names verbatim — a fix that shortened or truncated either one would still pass a looser
      // check, and would have closed the layout defect by deleting the feature.
      const hint = page.locator('p', { hasText: 'NEXT_PUBLIC_SUPABASE_URL' })
      const text = await hint.evaluate((el) => el.textContent)

      expect(text).toContain('NEXT_PUBLIC_SUPABASE_URL')
      expect(text).toContain('NEXT_PUBLIC_SUPABASE_ANON_KEY')
    })
  })
}
