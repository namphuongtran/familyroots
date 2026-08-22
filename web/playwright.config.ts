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

// S-042: `e2e/supabase-banner.spec.ts` measures the missing-Supabase banner
// (`SupabaseSetupNotice.tsx`) at 320px/200% text scale, which needs the opposite of
// `E2E_SUPABASE_ENV` above — both variables genuinely unset, on purpose, for that one spec. No
// other spec must lose the placeholders S-041 gives them, and a single dev-server process bakes
// in whichever `NEXT_PUBLIC_*` values it started with (Next.js inlines them once, at server
// start), so the only way to give one spec a different answer is a second, separate server.
export const BANNER_PORT = 3101
export const BANNER_BASE_URL = `http://127.0.0.1:${BANNER_PORT}`
const NO_SUPABASE_ENV = {
  // Explicit empty strings, not simply omitted: omitting a key lets the invoking shell's own
  // export (a developer's real `.env.local`-sourced shell, or a future CI job) leak through and
  // render the banner absent again, which is exactly the non-determinism S-041 closed for every
  // other spec. `getSupabaseEnv()` (`src/lib/supabase/config.ts:8`) treats `''` the same as
  // missing, via `!url || !anonKey`.
  NEXT_PUBLIC_SUPABASE_URL: '',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: '',
  // A second `next dev` sharing the primary server's `distDir` refuses to start ("Another next
  // dev server is already running" — Next.js's `experimental.lockDistDir`, on by default,
  // verified 2026-08-22). `web/next.config.ts` reads this to give the banner server its own
  // build directory so both processes can run for the whole suite without colliding.
  PLAYWRIGHT_SECOND_DIST_DIR: '.next-banner-e2e',
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
  webServer: [
    {
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
    {
      // S-042's dedicated server: same app, same host, genuinely no Supabase env. See
      // `NO_SUPABASE_ENV` above for why this can't be folded into the server above.
      command: `pnpm dev --port ${BANNER_PORT} --hostname 127.0.0.1`,
      url: BANNER_BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: NO_SUPABASE_ENV,
    },
  ],
})
