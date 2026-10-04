'use client'

/**
 * What a person can do to their session: sign in, sign out, register, onboard, pick a clan.
 *
 * None of these reads the session through `useSession`, so a component that only needs an action,
 * such as a sign-out button, adds no subscriber and no request. Each action that changes who the
 * user is or where they belong fetches the session itself, works out the access state with the
 * domain function, and routes on it through `landingPath`, the table every other router uses.
 *
 * The locale is the URL's (`useLocale`). The legacy hook routed on the profile's
 * `preferred_locale`, so a person reading `/en/login` could land on `/vi/dashboard`.
 */

import { useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useLocale } from 'next-intl'
import { useQueryClient } from '@tanstack/react-query'
import { accessStateOf } from '@/domain/session/access-state'
import type { Session } from '@/domain/session/session'
import { clearClanCookie, readCurrentClanId, writeClanCookie } from '@/shared/http/context.client'
import {
  signInWithOAuth,
  signInWithPassword,
  signOut as supabaseSignOut,
  supabaseErrorCode,
  type OAuthProvider,
} from '../api/supabase-auth'
import { landingPath } from '../model/landing'
import type {
  OnboardInput,
  OnboardResult,
  RegisterInput,
  RegistrationReceived,
} from '../model/session-dto'
import * as repository from '../server/auth-repository'
import { authRequestContext } from './auth-request-context'
import { clearSession, sessionQueryOptions } from './use-session'

/**
 * Supabase's code for a password sign-in by an account whose email is not confirmed yet
 * (`ErrorCode` in `@supabase/auth-js`). ADR-061 § 7 routes it to `/verify-email`, which made
 * `VerifyEmailScreen` reachable from a real sign-in for the first time.
 */
export const EMAIL_NOT_CONFIRMED_CODE = 'email_not_confirmed'

export interface OnboardingInput extends OnboardInput {
  /** Saved to the profile first, when the person typed one. */
  full_name?: string
}

export function useAuthActions() {
  const router = useRouter()
  const locale = useLocale()
  const queryClient = useQueryClient()

  /** Reads the session fresh and goes where it says. A ready user's clan becomes the cookie. */
  const routeOnFreshSession = useCallback(async (): Promise<Session | null> => {
    const session = await queryClient.fetchQuery({ ...sessionQueryOptions(), staleTime: 0 })
    const access = accessStateOf(session, readCurrentClanId())
    if (access.kind === 'ready') writeClanCookie(access.activeClan.clanId)
    router.push(landingPath(access, locale))
    return session
  }, [locale, queryClient, router])

  const signInWithEmail = useCallback(
    async (email: string, password: string): Promise<void> => {
      try {
        await signInWithPassword(email, password)
      } catch (error) {
        if (supabaseErrorCode(error) === EMAIL_NOT_CONFIRMED_CODE) {
          router.push(`/${locale}/verify-email?${new URLSearchParams({ email }).toString()}`)
          return
        }
        throw error
      }
      await routeOnFreshSession()
    },
    [locale, routeOnFreshSession, router],
  )

  const signInWithProvider = useCallback(
    (provider: OAuthProvider) => signInWithOAuth(provider, locale),
    [locale],
  )

  /**
   * A full page load to the login screen, not a client navigation: it drops every clan-scoped
   * cache with the session, which a `router.push` would keep.
   */
  const signOut = useCallback(async (): Promise<void> => {
    await supabaseSignOut()
    clearClanCookie()
    clearSession(queryClient)
    window.location.href = `/${locale}/login`
  }, [locale, queryClient])

  const register = useCallback(
    async (input: RegisterInput): Promise<RegistrationReceived> =>
      repository.register(input, { context: await authRequestContext() }),
    [],
  )

  const completeOnboarding = useCallback(
    async ({ full_name, ...input }: OnboardingInput): Promise<OnboardResult> => {
      const context = await authRequestContext()
      if (full_name?.trim()) {
        await repository.updateProfile({ full_name: full_name.trim() }, { context })
      }
      const result = await repository.onboard(input, { context })
      await routeOnFreshSession()
      return result
    },
    [routeOnFreshSession],
  )

  /**
   * The session does not change with the clan, so nothing is refetched: the cookie write
   * notifies `useCurrentClanId`, and every access state and clan-keyed query re-derives.
   */
  const selectClan = useCallback(async (clanId: string): Promise<string> => {
    const confirmed = await repository.selectClan(clanId, {
      context: await authRequestContext(),
    })
    writeClanCookie(confirmed)
    return confirmed
  }, [])

  return {
    signInWithEmail,
    signInWithGoogle: useCallback(() => signInWithProvider('google'), [signInWithProvider]),
    signInWithApple: useCallback(() => signInWithProvider('apple'), [signInWithProvider]),
    signOut,
    register,
    completeOnboarding,
    selectClan,
  }
}
