import { expect, test } from '@playwright/test'
import viMessages from '../messages/vi.json' with { type: 'json' }

test('an unknown path under a locale renders the localized 404 with status 404', async ({
  page,
}) => {
  const response = await page.goto('/vi/khong-ton-tai')
  expect(response?.status()).toBe(404)
  await expect(page.getByRole('heading', { name: viMessages.not_found.title })).toBeVisible()
  await expect(page.getByRole('link', { name: viMessages.not_found.home_link })).toBeVisible()
})
