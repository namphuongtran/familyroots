/**
 * Seed S-070: the inputs the authenticated e2e harness needs, in one file.
 *
 * **There is no session stub anywhere in this harness, and that is the whole design.**
 * S-070's own text says a session stub reachable in production is worse than no e2e
 * coverage at all. So nothing under `web/src/` knows this harness exists: the session is
 * obtained by typing a real password into the real `/vi/login` form and letting Supabase
 * issue a real ES256-signed token. `e2e/auth/no-session-bypass.guard.test.ts` is the standing
 * check that it stays that way, and `web/CLAUDE.md` ("The authenticated e2e harness")
 * carries the reasoning.
 *
 * The three inputs below are **required, not defaulted**, and `authStackEnv()` throws
 * naming the missing ones. A default would be the S-041 defect in a new costume: a run
 * that silently points at something other than the local stack, and reports a result about
 * a machine rather than about the code.
 */

/** `E2E_AUTH_STACK=1` is the only switch. Absent, every project below is not registered. */
export const AUTH_STACK_ENABLED = process.env.E2E_AUTH_STACK === '1'

/**
 * The four users `make seed` creates (`docs/ops/seed-test-users.md`, seed S-073). The
 * password is written down in that public document on purpose: the seeder refuses to run
 * against anything but a local stack.
 */
export const SEEDED_PASSWORD = 'dev-password-s073'

export interface SeededUser {
  readonly email: string
  /** The role `GET /me/clans` reports for this user in `clanSlug` below. */
  readonly role: 'admin' | 'editor' | 'viewer'
  readonly clanSlug: string
  /** Where `session.setup.ts` writes this user's captured cookies. */
  readonly storageState: string
}

/**
 * Two of S-073's four users, not all four. `admin` and `viewer` are the pair that differ
 * on every role-gated element on the members screen, so a case that reads one and not the
 * other is measuring the session's role rather than the markup. `editor` adds nothing the
 * admin reading does not already cover, and `outsider` belongs to the second clan, which
 * is a cross-clan isolation subject and not this seed's.
 */
export const SEEDED_USERS = {
  admin: {
    email: 'admin@familyroots.example.com',
    role: 'admin',
    clanSlug: 'nguyen-phuc',
    storageState: 'e2e/.auth/admin.json',
  },
  viewer: {
    email: 'viewer@familyroots.example.com',
    role: 'viewer',
    clanSlug: 'nguyen-phuc',
    storageState: 'e2e/.auth/viewer.json',
  },
} as const satisfies Record<string, SeededUser>

/**
 * The environment the authenticated dev server is started with. Every value is read from
 * the shell, so what a run targeted is visible in the command that ran it — the same rule
 * `make seed` follows (`docs/ops/seed-test-users.md`, "It reads three environment
 * variables").
 *
 * `E2E_AUTH_SUPABASE_URL` must be the string `supabase/config.toml` pins as
 * `[auth] external_url`'s origin, `http://supabase.localhost:54321`, and **not** the
 * `127.0.0.1` form `supabase status` prints. GoTrue stamps that string into every token as
 * `iss` and the backend rebuilds the expected issuer from its own `SUPABASE_URL`
 * (`backend/app/core/security.py:101`), so a mismatch yields `401 invalid_token` against a
 * healthy stack, with nothing in the 401 mentioning the issuer. Measured for S-072 and
 * recorded in `docs/ops/local-supabase.md`, "The two settings that are load bearing".
 */
export function authStackEnv(): Record<string, string> {
  const missing: string[] = []

  const required = (name: string): string => {
    const value = process.env[name]
    if (!value) {
      missing.push(name)
      return ''
    }
    return value
  }

  const supabaseUrl = required('E2E_AUTH_SUPABASE_URL')
  const supabaseAnonKey = required('E2E_AUTH_SUPABASE_ANON_KEY')
  const apiOrigin = required('E2E_AUTH_API_ORIGIN')

  if (missing.length > 0) {
    throw new Error(
      [
        `E2E_AUTH_STACK=1 was set but ${missing.join(', ')} ${missing.length === 1 ? 'is' : 'are'} missing.`,
        'The authenticated e2e projects need a running local Supabase stack, a running',
        'backend that trusts it, and both databases seeded. See web/CLAUDE.md,',
        '"The authenticated e2e harness", for the copy-paste block.',
      ].join('\n'),
    )
  }

  const origin = apiOrigin.replace(/\/+$/, '')

  return {
    NEXT_PUBLIC_SUPABASE_URL: supabaseUrl,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: supabaseAnonKey,
    // Three names for one backend, because three call sites read three different ones and
    // all of them are on the members screen's path. `NEXT_PUBLIC_API_ORIGIN` is the spine's
    // (`src/shared/http/api-client.ts:29`, origin only — it appends `/api/v1` itself);
    // `NEXT_PUBLIC_API_URL` is the legacy axios client's (`src/lib/api/axios.ts:6`, the full
    // base); `API_URL` is the server-side read ADR-056 added
    // (`src/lib/server/auth-context.ts:40`). Browser and dev server are both on the host
    // here, so one origin satisfies all three.
    NEXT_PUBLIC_API_ORIGIN: origin,
    NEXT_PUBLIC_API_URL: `${origin}/api/v1`,
    API_URL: `${origin}/api/v1`,
    // The same variable `next.config.ts` reads for S-042's banner server. Its name says
    // SECOND; what it means is "not the primary", and each extra `next dev` must pass its
    // own value or Next.js refuses to start on the shared `.next` lock.
    PLAYWRIGHT_SECOND_DIST_DIR: '.next-auth-e2e',
  }
}
