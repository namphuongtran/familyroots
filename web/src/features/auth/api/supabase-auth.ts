/**
 * The Supabase half of the slice's transport. Sign-in stays Supabase-direct (ADR-061 § 7): the
 * browser client holds the session and `@supabase/ssr` writes the cookie `middleware.ts` reads.
 * No React here, for `api-layer-has-no-react`.
 *
 * Every function returns or throws what Supabase gave it. Deciding what an error *means*, such
 * as `email_not_confirmed`, is the caller's job, so it stays testable against a fake client.
 */

import { createClientOrNull } from '@/lib/supabase/client'
import { createMissingSupabaseEnvError } from '@/lib/supabase/config'

export type OAuthProvider = 'google' | 'apple'

/** The auth events this slice reacts to. Supabase's own union, narrowed to a string here. */
export type AuthEvent = string

function requireClient() {
  const supabase = createClientOrNull()
  if (!supabase) throw createMissingSupabaseEnvError()
  return supabase
}

/**
 * Supabase answers a refused sign-in with `{ error }` rather than rejecting. This throws that
 * error as it came, an `AuthApiError` carrying `code` and `message`.
 */
export async function signInWithPassword(email: string, password: string): Promise<void> {
  const { error } = await requireClient().auth.signInWithPassword({ email, password })
  if (error) throw error
}

/**
 * Leaves the page for the provider. The provider returns to `/api/auth/callback`, which
 * exchanges the code for a session and redirects to `next`.
 */
export async function signInWithOAuth(provider: OAuthProvider, locale: string): Promise<void> {
  const { error } = await requireClient().auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: `${window.location.origin}/api/auth/callback?next=/${locale}/dashboard`,
    },
  })
  if (error) throw error
}

export async function signOut(): Promise<void> {
  await createClientOrNull()?.auth.signOut()
}

/** Returns the unsubscribe function. With no Supabase configured there is nothing to hear. */
export function onAuthStateChange(listener: (event: AuthEvent) => void): () => void {
  const supabase = createClientOrNull()
  if (!supabase) return () => {}
  const {
    data: { subscription },
  } = supabase.auth.onAuthStateChange((event) => listener(event))
  return () => subscription.unsubscribe()
}

/** The `code` Supabase put on an auth error, or null for anything else. */
export function supabaseErrorCode(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('code' in error)) return null
  const { code } = error as { code?: unknown }
  return typeof code === 'string' ? code : null
}
