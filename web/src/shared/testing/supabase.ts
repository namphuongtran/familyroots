import { vi } from 'vitest'

/**
 * A stand-in for the Supabase browser client, for tests that mock
 * `@/lib/supabase/client`'s `createClientOrNull`:
 *
 * ```ts
 * vi.mock('@/lib/supabase/client', () => ({ createClientOrNull: vi.fn() }))
 * vi.mocked(createClientOrNull).mockReturnValue(fake.client as never)
 * ```
 *
 * It holds a session or none, answers a password sign-in with the `{ error }` a refusal
 * carries, and lets a test emit an auth event to every live listener. The backend half of a
 * test still goes through MSW; this only replaces what the browser asks Supabase.
 */

export interface FakeSupabaseOptions {
  /** The access token of the stored session, or null for no session. */
  accessToken?: string | null
  /** What `signInWithPassword` answers with, the shape `AuthApiError` has. */
  signInError?: { code: string; message: string; status?: number } | null
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
  }

  return {
    client: { auth },
    auth,
    /** Sends an auth event to every listener still subscribed. */
    emit(event: string) {
      for (const listener of listeners) listener(event, session())
    },
    listenerCount: () => listeners.size,
    setAccessToken(next: string | null) {
      accessToken = next
    },
  }
}
