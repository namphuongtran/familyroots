import { defineConfig, devices } from '@playwright/test'
import { AUTH_STACK_ENABLED, authStackEnv } from './e2e/auth/fixtures'

const PORT = 3100
// Exported for `e2e/auth/members.auth.spec.ts`, which replays a real captured session
// against this hermetic server on purpose — see that file's "does not travel" case.
export const BASE_URL = `http://127.0.0.1:${PORT}`

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

/**
 * Seed S-070: the third `next dev`, the only one with a session.
 *
 * **Why a third server and not the primary one.** The primary server on :3100 is
 * deliberately hermetic (S-041): fake Supabase placeholders, no network dependency, same
 * result in a fresh clone, in a worktree and in CI. Pointing it at the local Supabase
 * stack would make every existing spec depend on Docker, which is a regression for every
 * other seed. A `next dev` process bakes its `NEXT_PUBLIC_*` values in at start, so one
 * server cannot answer both questions — the same reason S-042 needed its own.
 *
 * **Why an explicit opt-in and not auto-detection.** `E2E_AUTH_STACK=1` is the switch, and
 * `pnpm test:e2e:auth` is the only thing that sets it. Auto-detecting a reachable stack
 * and skipping when it is absent was rejected: a suite that quietly covers nothing when
 * Docker is down is the "passed because it scanned nothing" failure `.claude/rules/seeds.md`
 * names, and it is invisible in a green run. With the switch, the projects either run or do
 * not exist, and `authStackEnv()` throws by name when the switch is on and an input is not.
 */
const AUTH_PORT = 3102
export const AUTH_BASE_URL = `http://127.0.0.1:${AUTH_PORT}`

/**
 * Everything under `e2e/auth/`, for the hermetic projects to ignore. `*.guard.test.ts`
 * matches this too, which is intentional: it is a Vitest file (`vitest.config.mts`'s unit
 * include names it) and must never be run by Playwright.
 */
const AUTH_SPECS = /[\\/]e2e[\\/]auth[\\/]/

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
    // S-070: `testIgnore` keeps the hermetic pair off `e2e/auth/`, whose specs need a
    // session and a running stack. Without it these two would pick those files up and fail
    // on a machine with no Docker, which is the S-041 guarantee this must not break.
    { name: 'chromium', testIgnore: AUTH_SPECS, use: { ...devices['Desktop Chrome'] } },
    // Most members will arrive on a phone — keep a mobile viewport in the loop
    // from the start rather than discovering layout breakage in sub-project B.
    { name: 'mobile', testIgnore: AUTH_SPECS, use: { ...devices['Pixel 5'] } },
    ...(AUTH_STACK_ENABLED
      ? [
          {
            // Logs in through the real form and writes the cookies to `e2e/.auth/`.
            name: 'auth-setup',
            testMatch: /e2e\/auth\/session\.setup\.ts$/,
            use: { ...devices['Desktop Chrome'], baseURL: AUTH_BASE_URL },
          },
          {
            name: 'auth-chromium',
            testMatch: /e2e\/auth\/.*\.auth\.spec\.ts$/,
            dependencies: ['auth-setup'],
            use: { ...devices['Desktop Chrome'], baseURL: AUTH_BASE_URL },
          },
        ]
      : []),
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
    // S-070's server, registered only when `E2E_AUTH_STACK=1`. `authStackEnv()` reads the
    // local stack's URL, its anon key and the backend origin from the shell and throws
    // naming whatever is missing, so a half-configured run fails before a browser opens
    // rather than reporting a redirect to /vi/login as a product defect.
    ...(AUTH_STACK_ENABLED
      ? [
          {
            command: `pnpm dev --port ${AUTH_PORT} --hostname 127.0.0.1`,
            url: AUTH_BASE_URL,
            reuseExistingServer: !process.env.CI,
            timeout: 120_000,
            env: authStackEnv(),
          },
        ]
      : []),
  ],
})
