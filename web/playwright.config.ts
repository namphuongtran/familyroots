import { defineConfig, devices } from '@playwright/test'

const PORT = 3100
const BASE_URL = `http://127.0.0.1:${PORT}`

// S-041: the e2e gate must give the same result on a fresh clone, in a git
// worktree, and in CI, without a `web/.env.local` — which git does not carry
// and which every `git worktree` lacks. Without these two variables the app
// renders the missing-Supabase banner (`SupabaseSetupNotice.tsx`), and
// `text-scale.spec.ts` then measures a real overflow caused by that banner,
// not by the code under test. See docs/SEEDS.md S-041 for the measurements.
//
// These are obviously-fake values: an unresolvable `.example.` hostname and a
// key that spells out what it is, not a token shape anyone could copy into a
// real client as a credential. They are picked up only if the shell running
// `pnpm test:e2e` did not already export the two variables, so a CI job (or a
// developer) that exports the real placeholders — `web-ci.yml`'s `e2e` job
// already does — is not overridden. They fill in for `pnpm dev`'s own env,
// which is what `webServer.command` below spawns, and Next.js's env-file
// loader never overwrites a variable already present in `process.env` when
// the process starts — so this wins over `.env.local` even when one is
// present in the primary checkout. That is intentional and not a conflict:
// no e2e spec talks to a live Supabase backend (out of scope, S-041), so the
// e2e run does not need — and must not depend on — real credentials.
const E2E_SUPABASE_ENV = {
  NEXT_PUBLIC_SUPABASE_URL:
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? 'https://e2e-fake-project.example.supabase.co',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? 'e2e-fake-anon-key',
}

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
    env: E2E_SUPABASE_ENV,
  },
})
