import type { AuthSessionPort, SessionUser } from '@/application/auth/ports/auth-repository'
import { createClientOrNull } from '@/lib/supabase/client'
import { createMissingSupabaseEnvError } from '@/lib/supabase/config'

function mapSupabaseUser(user: {
  id: string
  email?: string | null
  user_metadata?: Record<string, unknown>
}): SessionUser {
  return {
    id: user.id,
    email: user.email ?? '',
    metadata: user.user_metadata,
  }
}

export class SupabaseAuthSessionPort implements AuthSessionPort {
  async getSessionUser(): Promise<SessionUser | null> {
    const supabase = createClientOrNull()
    if (!supabase) {
      return null
    }
    const {
      data: { session },
    } = await supabase.auth.getSession()

    if (!session?.user) {
      return null
    }

    return mapSupabaseUser(session.user)
  }

  onAuthStateChange(callback: (user: SessionUser | null) => void): () => void {
    const supabase = createClientOrNull()
    if (!supabase) {
      callback(null)
      return () => {}
    }
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      callback(session?.user ? mapSupabaseUser(session.user) : null)
    })

    return () => subscription.unsubscribe()
  }

  async signInWithEmail(email: string, password: string): Promise<void> {
    const supabase = createClientOrNull()
    if (!supabase) {
      throw createMissingSupabaseEnvError()
    }
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      throw error
    }
  }

  async signInWithOAuth(provider: 'google' | 'apple'): Promise<void> {
    const supabase = createClientOrNull()
    if (!supabase) {
      throw createMissingSupabaseEnvError()
    }
    const locale =
      typeof window !== 'undefined' ? window.location.pathname.split('/')[1] || 'vi' : 'vi'
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/api/auth/callback?next=/${locale}/dashboard`,
      },
    })
    if (error) {
      throw error
    }
  }

  async signOut(): Promise<void> {
    const supabase = createClientOrNull()
    if (!supabase) {
      return
    }
    await supabase.auth.signOut()
  }
}

export const authSessionPort = new SupabaseAuthSessionPort()
