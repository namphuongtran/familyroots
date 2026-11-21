import { expect, test } from '@playwright/test'

/** #319: reads the real response headers from a real Next server. */
test('/vi/login carries the security headers and refuses framing', async ({ request }) => {
  const response = await request.get('/vi/login')
  const h = response.headers()
  const csp = h['content-security-policy']
  expect(csp).toBeTruthy()
  expect(csp).toContain("frame-ancestors 'none'")
  expect(csp).toContain("object-src 'none'")
  expect(h['x-content-type-options']).toBe('nosniff')
  expect(h['referrer-policy']).toBe('strict-origin-when-cross-origin')
  expect(h['permissions-policy']).toContain('camera=()')
})

test('the invitation route keeps Referrer-Policy: no-referrer and the CSP', async ({ request }) => {
  const response = await request.get('/vi/invitations/some-token')
  const h = response.headers()
  expect(h['referrer-policy']).toBe('no-referrer')
  expect(h['content-security-policy']).toContain("frame-ancestors 'none'")
})
