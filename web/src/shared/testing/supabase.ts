import { vi } from 'vitest'

/**
 * A stand-in for the Supabase browser client, for tests that mock
 * `@/shared/supabase/client`'s `createClientOrNull`:
 *
 * ```ts
 * vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))
 * vi.mocked(createClientOrNull).mockReturnValue(fake.client as never)
 * ```
 *
 * It holds a session or none, answers a password sign-in with the `{ error }` a refusal
 * carries, refreshes the session or refuses to, and lets a test emit an auth event to every live
 * listener. The backend half of a
 * test still goes through MSW; this only replaces what the browser asks Supabase.
 */

export interface FakeSupabaseOptions {
  /** The access token of the stored session, or null for no session. */
  accessToken?: string | null
  /** What `signInWithPassword` answers with, the shape `AuthApiError` has. */
  signInError?: { code: string; message: string; status?: number } | null
  /**
   * The access token `refreshSession` rotates to. Absent or null, Supabase refuses the refresh,
   * as it does for a refresh token that is gone.
   */
  refreshedAccessToken?: string | null
  /** How long `refreshSession` takes, so that concurrent callers can overlap one refresh. */
  refreshDelayMs?: number
}

type Listener = (event: string, session: unknown) => void

export function fakeSupabaseClient(options: FakeSupabaseOptions = {}) {
  let accessToken = options.accessToken ?? null
  const listeners = new Set<Listener>()

  const session = () =>
    accessToken === null
      ? null
      : { access_token: accessToken, user: { id: 'supabase-user-1', email: 'lan@example.com' } }

  const auth = {
    getSession: vi.fn(async () => ({ data: { session: session() }, error: null })),
    onAuthStateChange: vi.fn((listener: Listener) => {
      listeners.add(listener)
      return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } }
    }),
    signInWithPassword: vi.fn(async () => {
      // An `Error`, as Supabase's `AuthApiError` is, so a screen that shows `error.message` shows it.
      const refusal = options.signInError ?? null
      const error =
        refusal === null
          ? null
          : Object.assign(new Error(refusal.message), { name: 'AuthApiError', ...refusal })
      if (error === null) accessToken = accessToken ?? 'signed-in-token'
      return { data: { session: error ? null : session() }, error }
    }),
    signInWithOAuth: vi.fn(async () => ({ data: {}, error: null })),
    signOut: vi.fn(async () => {
      accessToken = null
      return { error: null }
    }),
    /**
     * Supabase's own order, read in `@supabase/auth-js` 2.111 `_callRefreshToken`: the new
     * session is stored and `TOKEN_REFRESHED` reaches every listener before the call resolves.
     */
    refreshSession: vi.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, options.refreshDelayMs ?? 0))
      const next = options.refreshedAccessToken ?? null
      if (next === null) {
        const error = Object.assign(new Error('Invalid Refresh Token: Refresh Token Not Found'), {
          name: 'AuthApiError',
          code: 'refresh_token_not_found',
          status: 400,
        })
        return { data: { session: null, user: null }, error }
      }
      accessToken = next
      emit('TOKEN_REFRESHED')
      return { data: { session: session(), user: session()?.user ?? null }, error: null }
    }),
  }

  function emit(event: string): void {
    for (const listener of listeners) listener(event, session())
  }

  return {
    client: { auth },
    auth,
    /** Sends an auth event to every listener still subscribed. */
    emit,
    listenerCount: () => listeners.size,
    setAccessToken(next: string | null) {
      accessToken = next
    },
  }
}

/**
 * The body GoTrue answers `GET /auth/v1/settings` with, for a test that serves it through MSW.
 * Copied whole from the hosted project `xkmutzxdhdigyfisfrwd` on 2026-10-24 (#290), where every
 * provider but `email` was off. A test switches providers on through `external`; nothing else in
 * the shape is invented.
 */
export function gotrueSettings(external: Partial<Record<string, boolean>> = {}) {
  return {
    external: {
      anonymous_users: false,
      apple: false,
      azure: false,
      bitbucket: false,
      discord: false,
      facebook: false,
      snapchat: false,
      figma: false,
      fly: false,
      github: false,
      gitlab: false,
      google: false,
      keycloak: false,
      kakao: false,
      linkedin: false,
      linkedin_oidc: false,
      notion: false,
      spotify: false,
      slack: false,
      slack_oidc: false,
      workos: false,
      twitch: false,
      twitter: false,
      email: true,
      phone: false,
      zoom: false,
      ...external,
    },
    disable_signup: false,
    mailer_autoconfirm: false,
    phone_autoconfirm: false,
    sms_provider: 'twilio',
    saml_enabled: false,
    saml_private_key_next_configured: true,
    passkeys_enabled: false,
  }
}
