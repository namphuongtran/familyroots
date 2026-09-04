import { expect, test } from '@playwright/test'

/**
 * Assertions the unit and component suites structurally cannot make: that
 * middleware, the always-on locale prefix, and route protection agree with each
 * other in a real browser against a real Next server.
 *
 * Real journeys (login, clan switching, tree) arrive with the auth and persons
 * slices, which need a backend.
 */

test('the root redirects to the Vietnamese locale prefix', async ({ page }) => {
  // Verified against a live dev server: `/` 307s to `/vi/login` when there is no
  // session, and to `/vi` when Supabase is unconfigured. The regex covers both,
  // so this passes with or without placeholder credentials in the environment.
  await page.goto('/')
  await expect(page).toHaveURL(/\/vi(\/|$)/)
})

test('the login page renders and carries a sign-in form', async ({ page }) => {
  const response = await page.goto('/vi/login')
  expect(response?.status()).toBeLessThan(400)
  await expect(page.locator('form')).toBeVisible()
})

/**
 * Was a ratchet over a real defect; now a real assertion.
 *
 * `src/app/layout.tsx` used to hardcode `<html lang="en">`, so every Vietnamese
 * page told assistive technology it was English — screen readers applied the
 * wrong pronunciation rules to the entire product. The `<html lang>` fix fixed it:
 * `RootLayout` now reads the negotiated locale with next-intl's `getLocale()`
 * (a request-scoped read of the header the intl middleware sets, not tied to
 * which layout calls it) rather than hardcoding a value, so `<html lang>`
 * reflects the URL's locale prefix even though `<html>` itself still lives in
 * the layout above `[locale]` — `src/app/page.tsx` and `src/app/api/*` share
 * that same root layout and are outside the `[locale]` segment, and React does
 * not allow a second, nested `<html>` inside it.
 *
 * This was a `test.fail()` before the fix: CI stayed green while the bug
 * existed, and would have turned RED the moment someone fixed it without
 * updating this test. That is the opposite of `test.skip`, which would have
 * let the fix land unnoticed and the coverage never come back.
 */
test('the page declares Vietnamese to assistive technology', async ({ page }) => {
  await page.goto('/vi/login')
  await expect(page.locator('html')).toHaveAttribute('lang', 'vi', { timeout: 3000 })
})

// Same fix, a different locale prefix — proves `lang` tracks the route rather
// than being a second hardcoded value that happens to read `vi`.
test('the page declares English to assistive technology under /en', async ({ page }) => {
  await page.goto('/en/login')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en', { timeout: 3000 })
})
