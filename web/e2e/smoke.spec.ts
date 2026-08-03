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
 * A ratchet over a real defect, not a skipped test.
 *
 * `src/app/layout.tsx` hardcodes `<html lang="en">`, so every Vietnamese page
 * currently tells assistive technology it is English — screen readers apply the
 * wrong pronunciation rules to the entire product. The `[locale]` layout renders
 * a `<div>`, not an `<html>`, so the locale never reaches the attribute.
 *
 * Fixing it means moving `<html>`/`<body>` into a locale-aware layout while
 * `src/app/page.tsx` and `src/app/api/*` still live outside `[locale]` — real
 * work that belongs to PR 1 (auth), which already rewrites the locale, cookie and
 * middleware machinery. It is not harness work.
 *
 * `test.fail()` means: this is expected to fail today. CI stays green while the
 * bug exists, and turns RED the moment someone fixes it — at which point delete
 * `.fail` and keep the assertion. That is the opposite of `test.skip`, which
 * would let the fix land unnoticed and the coverage never come back.
 */
test.fail('the page declares Vietnamese to assistive technology', async ({ page }) => {
  await page.goto('/vi/login')
  await expect(page.locator('html')).toHaveAttribute('lang', 'vi', { timeout: 3000 })
})
