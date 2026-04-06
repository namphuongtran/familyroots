'use client'

import { useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import type { RegisterResult } from '@/application/auth/ports/auth-repository'
import {
  hydrateAuthContext,
  selectActiveClan,
} from '@/application/auth/use-cases/auth-context'
import { authProfileRepository } from '@/infrastructure/auth/http-auth-profile-repository'
import { authSessionPort } from '@/infrastructure/auth/supabase-auth-session-port'
import { useAuthStore } from '@/store/auth.store'

export function useAuth() {
  const {
    user,
    currentClanId,
    clanMemberships,
    isLoading,
    isPendingApproval,
    needsClanSelection,
    setUser,
    setCurrentClan,
    setClanMemberships,
    setLoading,
    setAccessState,
    clear,
  } = useAuthStore()
  const router = useRouter()

  const syncAuthContext = useCallback(async () => {
    const preferredClanId =
      typeof window !== 'undefined' ? localStorage.getItem('current_clan_id') ?? undefined : undefined
    const context = await hydrateAuthContext(authSessionPort, authProfileRepository, preferredClanId)
    if (!context.user) {
      clear()
      return
    }

    setUser(context.user)
    setClanMemberships(context.clanMemberships)

    const activeClanId = context.currentClanId ?? context.user.clan_id
    setCurrentClan(activeClanId)
    setAccessState({
      isPendingApproval: context.isPendingApproval,
      needsClanSelection: context.needsClanSelection,
    })

    if (typeof window !== 'undefined') {
      if (activeClanId) {
        localStorage.setItem('current_clan_id', activeClanId)
      } else {
        localStorage.removeItem('current_clan_id')
      }
      localStorage.setItem('preferred_locale', context.user.preferred_locale)
    }
  }, [clear, setAccessState, setClanMemberships, setCurrentClan, setUser])

  // Sync Supabase session → auth store on mount and on auth state change
  useEffect(() => {
    let isMounted = true
    setLoading(true)

    syncAuthContext().finally(() => {
      if (isMounted) {
        setLoading(false)
      }
    })

    const unsubscribe = authSessionPort.onAuthStateChange(() => {
      syncAuthContext().finally(() => {
        if (isMounted) {
          setLoading(false)
        }
      })
    })

    return () => {
      isMounted = false
      unsubscribe()
    }
  }, [setLoading, syncAuthContext])

  const signInWithEmail = useCallback(
    async (email: string, password: string) => {
      await authSessionPort.signInWithEmail(email, password)
      const context = await hydrateAuthContext(authSessionPort, authProfileRepository)
      await syncAuthContext()

      if (context.isPendingApproval) {
        router.push(`/${context.user?.preferred_locale ?? 'vi'}/pending-approval`)
        return
      }

      router.push(`/${context.user?.preferred_locale ?? 'vi'}/dashboard`)
    },
    [router, syncAuthContext],
  )

  const signInWithGoogle = useCallback(async () => {
    await authSessionPort.signInWithOAuth('google')
  }, [])

  const signInWithApple = useCallback(async () => {
    await authSessionPort.signInWithOAuth('apple')
  }, [])

  const signOut = useCallback(async () => {
    await authSessionPort.signOut()
    clear()

    const locale = user?.preferred_locale ?? 'vi'
    if (typeof window !== 'undefined') {
      localStorage.removeItem('current_clan_id')
      window.location.href = `/${locale}/login`
    }
  }, [clear, user?.preferred_locale])

  const selectClan = useCallback(
    async (clanId: string) => {
      const selectedClanId = await selectActiveClan(authProfileRepository, clanId)
      setCurrentClan(selectedClanId)

      if (typeof window !== 'undefined') {
        localStorage.setItem('current_clan_id', selectedClanId)
      }

      await syncAuthContext()
      return selectedClanId
    },
    [setCurrentClan, syncAuthContext],
  )

  return {
    user,
    currentClanId,
    clanMemberships,
    isLoading,
    isPendingApproval,
    needsClanSelection,
    isAuthenticated: !!user,
    isApproved: !isPendingApproval,
    signInWithEmail,
    signInWithGoogle,
    signInWithApple,
    signOut,
    selectClan,
    syncAuthContext,
  }
}

// Convenience alias used by auth pages
export function useAuthActions() {
  const { signInWithEmail, signOut } = useAuth()

  const signIn = useCallback(
    async (email: string, password: string) => {
      await signInWithEmail(email, password)
    },
    [signInWithEmail],
  )

  const signUp = useCallback(
    async (input: {
      email: string
      password: string
      full_name: string
      clan_action: 'join' | 'create'
      clan_id?: string
      clan_name?: string
      clan_slug?: string
    }): Promise<RegisterResult> => {
      return authProfileRepository.register(input)
    },
    [],
  )

  return { signIn, signUp, signOut }
}
