import { defineConfig, devices } from '@playwright/test'

const PORT = 3100
const BASE_URL = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    // Vietnamese is the default locale; test the default path, not the exception.
    locale: 'vi-VN',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // Most members will arrive on a phone — keep a mobile viewport in the loop
    // from the start rather than discovering layout breakage in sub-project B.
    { name: 'mobile', use: { ...devices['Pixel 5'] } },
  ],
  webServer: {
    // Bind the dev server to the same host the tests navigate to. With the default
    // bind, Next treats 127.0.0.1 as a cross-origin dev client and blocks
    // /_next/webpack-hmr on every run — harmless noise now, but noise that would
    // hide a real cross-origin problem once the slices add journeys.
    command: `pnpm dev --port ${PORT} --hostname 127.0.0.1`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
