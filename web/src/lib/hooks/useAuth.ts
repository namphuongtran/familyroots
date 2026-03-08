'use client'

import { useCallback, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useAuthStore } from '@/store/auth.store'
import type { UserProfile } from '@/lib/types'

export function useAuth() {
  const { user, isLoading, setUser, setLoading, clear } = useAuthStore()
  const supabase = createClient()

  // Sync Supabase session → auth store on mount and on auth state change
  useEffect(() => {
    setLoading(true)

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        const meta = session.user.user_metadata
        setUser({
          id: session.user.id,
          email: session.user.email ?? '',
          full_name: meta?.full_name ?? '',
          clan_id: meta?.clan_id,
          clan_name: meta?.clan_name,
          role: meta?.clan_role,
          is_approved: meta?.is_approved ?? false,
          member_id: meta?.member_id,
          preferred_locale: meta?.preferred_locale ?? 'vi',
        } satisfies UserProfile)
      } else {
        clear()
      }
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        const meta = session.user.user_metadata
        setUser({
          id: session.user.id,
          email: session.user.email ?? '',
          full_name: meta?.full_name ?? '',
          clan_id: meta?.clan_id,
          clan_name: meta?.clan_name,
          role: meta?.clan_role,
          is_approved: meta?.is_approved ?? false,
          member_id: meta?.member_id,
          preferred_locale: meta?.preferred_locale ?? 'vi',
        })
      } else {
        clear()
      }
    })

    return () => subscription.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const signInWithEmail = useCallback(
    async (email: string, password: string) => {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      return data
    },
    [supabase],
  )

  const signInWithGoogle = useCallback(async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })
    if (error) throw error
  }, [supabase])

  const signInWithApple = useCallback(async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'apple',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })
    if (error) throw error
  }, [supabase])

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
    clear()
    window.location.href = '/login'
  }, [supabase, clear])

  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    isApproved: user?.is_approved ?? false,
    signInWithEmail,
    signInWithGoogle,
    signInWithApple,
    signOut,
  }
}

// Convenience alias used by auth pages
export function useAuthActions() {
  const { signInWithEmail, signOut } = useAuth()
  const supabase = createClient()

  const signIn = useCallback(
    async (email: string, password: string) => signInWithEmail(email, password),
    [signInWithEmail],
  )

  const signUp = useCallback(
    async (email: string, password: string, fullName: string) => {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { full_name: fullName },
          emailRedirectTo: `${window.location.origin}/api/auth/callback`,
        },
      })
      if (error) throw error
      return data
    },
    [supabase],
  )

  return { signIn, signUp, signOut }
}

