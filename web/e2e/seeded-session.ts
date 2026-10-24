import type { Page } from '@playwright/test'
import type { components } from '../src/generated/api-types'

/**
 * A signed-in browser for the hermetic suite, with no Supabase behind it. Moved here from
 * `invitation-accept.spec.ts` when the register specs needed it too (#291): the clan fields
 * live on onboarding now, which only a signed-in person reaches. The cookie is a fixture, and
 * so is every backend answer a spec routes beside it.
 */

/**
 * The cookie `@supabase/ssr`'s browser client reads a session out of.
 *
 * `createBrowserClient` (`src/shared/supabase/client.ts:11`) stores the session in
 * `document.cookie`, not `localStorage` — that is the point of the SSR package.
 * The name is `sb-${hostname.split('.')[0]}-auth-token`
 * (`node_modules/@supabase/supabase-js/dist/index.mjs:680`). The value is `base64-`
 * followed by the base64url of the session JSON
 * (`@supabase/ssr/dist/main/cookies.js:9,45`).
 *
 * Seeding it is the only way to reach the signed-in states in a browser: accept
 * requires a session (`docs/contracts/rest-invitations-api.md:62-64`), onboarding
 * renders its clan step only for one (#291), and no hermetic spec has a real Supabase
 * to sign in against. Nothing is asserted about
 * Supabase itself — the session is a fixture, and the page's own behaviour is what
 * is measured.
 *
 * **This name is DERIVED, and it used to be the literal
 * `'sb-e2e-fake-project-auth-token'`.** That literal was true locally and false in
 * CI, which is where it was caught: `.github/workflows/web-ci.yml` runs the e2e job
 * with `NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co`, while
 * `playwright.config.ts` falls back to `https://e2e-fake-project.example.supabase.co`
 * only when that variable is unset. So in CI the app read
 * `sb-placeholder-auth-token`, the seeded cookie was ignored, the page rendered its
 * signed-out state, and four cases failed on a missing Accept button rather than on
 * anything they were written to measure.
 *
 * Derive it from the same expression `playwright.config.ts` uses, so the two cannot
 * drift again. `e2e/auth/session.setup.ts:61` already had the robust shape — it
 * matches on `startsWith('sb-')` and `endsWith('-auth-token')` rather than a literal.
 */
function sessionCookieName(): string {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? 'https://e2e-fake-project.example.supabase.co'
  return `sb-${new URL(url).hostname.split('.')[0]}-auth-token`
}

export const SESSION_COOKIE_NAME = sessionCookieName()

/** Who the seeded session is. The cookie and the routed `GET /auth/me` both name this person. */
const SEEDED_IDENTITY = {
  id: '9f1c4f7e-0000-4000-8000-0000000000aa',
  email: 'invited@example.com',
  fullName: 'Người Được Mời',
} as const

function sessionCookieValue(): string {
  const session = {
    access_token: 'e2e-access-token',
    token_type: 'bearer',
    expires_in: 3600,
    // Far enough out that auth-js never tries a refresh against the fake host.
    expires_at: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 365,
    refresh_token: 'e2e-refresh-token',
    user: {
      id: SEEDED_IDENTITY.id,
      aud: 'authenticated',
      role: 'authenticated',
      email: SEEDED_IDENTITY.email,
      app_metadata: {},
      user_metadata: { full_name: SEEDED_IDENTITY.fullName },
      identities: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  }
  return `base64-${Buffer.from(JSON.stringify(session)).toString('base64url')}`
}

export async function signIn(page: Page): Promise<void> {
  await page.context().addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: sessionCookieValue(),
      domain: '127.0.0.1',
      path: '/',
    },
  ])
}

/**
 * Signed in, holding no membership: `accessStateOf`'s `needs-onboarding`, the state
 * `landingPath` sends to `/{locale}/register?mode=oauth`. `GET /auth/me` answers the profile
 * with no clan, and `GET /me/clans` an empty list, in the envelope the backend sends. A
 * `PATCH /auth/me`, the full-name save onboarding sends first, answers the backend's
 * `MessageData`. Each body is typed by the generated schema, so a contract change fails
 * `pnpm type-check` here rather than leaving a stub the app no longer parses.
 */
export async function signInWithNoClan(page: Page): Promise<void> {
  await signIn(page)
  const profile = {
    id: SEEDED_IDENTITY.id,
    email: SEEDED_IDENTITY.email,
    full_name: SEEDED_IDENTITY.fullName,
    clan_id: null,
    clan_name: null,
    role: null,
    is_approved: false,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  } satisfies components['schemas']['UserProfile']
  const saved = { message: 'ok' } satisfies components['schemas']['MessageData']
  const noClans: components['schemas']['UserClanMembership'][] = []
  await page.route('**/api/v1/auth/me', async (route) => {
    const body = { data: route.request().method() === 'GET' ? profile : saved }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
  await page.route('**/api/v1/me/clans', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: noClans }),
    }),
  )
}
