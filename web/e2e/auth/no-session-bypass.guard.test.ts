import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * the authenticated e2e harness's fence, and the reason it is a test and not a sentence in a document.
 *
 * The authenticated e2e harness has no switch. It cannot be enabled in production because
 * there is nothing in the shipped app to enable: `web/playwright.config.ts` and `web/e2e/`
 * are not imported by anything under `web/src/`, so `pnpm build` never sees them. The
 * session a spec holds was obtained by typing a real password into `/vi/login`, and it is
 * signed by the local stack's key.
 *
 * **That is a property of the tree today, and a property has to be kept.** The cheap way
 * to break it is the obvious one: a later agent, wanting a faster suite, adds
 * `if (process.env.E2E_AUTH_STACK) return fakeSession` inside `getServerAuthContext` and
 * every case here still passes, faster. This file is what fails then. It is deliberately a
 * grep and not a type: the defect it catches is the *existence* of a new code path, and a
 * type cannot see one that does not exist yet.
 *
 * **Naming.** `*.guard.test.ts` runs under `vitest --project unit` (its include glob in
 * `vitest.config.mts` names it) and under no Playwright project. It lives beside the
 * harness because it is about the harness, not about the module it scans.
 */

/** `web/`, two levels up from `web/e2e/auth/`. */
const WEB_ROOT = join(import.meta.dirname, '..', '..')
const SRC_ROOT = join(WEB_ROOT, 'src')

/**
 * Every marker the harness introduces, plus the two generic shapes a session bypass takes.
 * A hit under `src/` means shipped code has learned that a test harness exists, which is
 * the whole thing the authenticated e2e harness was told to prevent: "a session stub that can be reached in
 * production is worse than no e2e coverage at all."
 */
const FORBIDDEN_IN_SRC: readonly { readonly pattern: RegExp; readonly why: string }[] = [
  {
    pattern: /\bE2E_[A-Z0-9_]+/,
    why: 'an env var from the authenticated e2e harness (web/e2e/auth/fixtures.ts). Shipped code must not branch on it — that is the session stub the authenticated e2e harness refused to build.',
  },
  {
    pattern: /PLAYWRIGHT/,
    why: 'a Playwright-only variable. `next.config.ts` may read one (the banner spec needs a separate distDir); nothing under src/ has a reason to.',
  },
  {
    pattern: /storageState/,
    why: "Playwright's captured-cookie file. Only e2e/ writes or reads one.",
  },
  {
    pattern: /e2e\/\.auth/,
    why: 'the directory the harness writes sessions into. Shipped code must not know its name.',
  },
]

function sourceFilesUnder(directory: string): string[] {
  const found: string[] = []

  for (const entry of readdirSync(directory)) {
    const absolute = join(directory, entry)
    if (statSync(absolute).isDirectory()) {
      found.push(...sourceFilesUnder(absolute))
    } else if (/\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/.test(entry)) {
      found.push(absolute)
    }
  }

  return found
}

describe('the authenticated e2e harness cannot be reached from shipped code', () => {
  const files = sourceFilesUnder(SRC_ROOT)

  /**
   * A guard that scanned nothing would pass. `.claude/rules/testing.md` calls that "worse
   * than no check", so the file count is asserted before the contents are: 100 is far
   * below the 300-odd files `src/` holds today and far above zero, so this fails on a
   * broken path rather than on a refactor.
   */
  it('scanned the real src tree', () => {
    expect(files.length).toBeGreaterThan(100)
  })

  for (const { pattern, why } of FORBIDDEN_IN_SRC) {
    it(`no file under src/ mentions ${String(pattern)} — ${why}`, () => {
      const offenders = files
        .filter((file) => pattern.test(readFileSync(file, 'utf8')))
        .map((file) => relative(WEB_ROOT, file))

      expect(offenders).toEqual([])
    })
  }

  it('no file under src/ imports anything from e2e/', () => {
    const offenders = files
      .filter((file) => /from\s+['"][^'"]*\be2e\//.test(readFileSync(file, 'utf8')))
      .map((file) => relative(WEB_ROOT, file))

    expect(offenders).toEqual([])
  })
})
