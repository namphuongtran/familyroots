import { expect, test } from '@playwright/test'

/** #366: an unknown path under a locale lands on the localized 404, with status 404. */
test('an unknown Vietnamese path renders the Vietnamese 404', async ({ page }) => {
  const response = await page.goto('/vi/khong-ton-tai')
  expect(response?.status()).toBe(404)
  await expect(page.getByRole('heading', { name: 'Không tìm thấy trang' })).toBeVisible()
})
