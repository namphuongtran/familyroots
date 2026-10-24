'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useAuthActions } from '../hooks/use-auth-actions'
import { useOAuthProviders } from '../hooks/use-oauth-providers'
import { SECONDARY_LINK } from './auth-action-classes'
import { AuthWordmark } from './AuthWordmark'
import { SupabaseSetupNotice } from './SupabaseSetupNotice'

/** What `/api/auth/callback` puts on the URL when a provider's code does not become a session. */
const OAUTH_CALLBACK_FAILED = 'auth_callback_failed'

/**
 * The sign-in screen. `app/[locale]/(auth)/login/page.tsx` only routes here.
 *
 * A refused sign-in shows Supabase's own message, except `email_not_confirmed`, which
 * `signInWithEmail` routes to `/verify-email` before anything reaches this screen's catch.
 *
 * Google is offered only while the Supabase project has it on (`useOAuthProviders`, #290). A
 * failed Google return lands here with `?error=auth_callback_failed`, and the screen says so in
 * the reader's locale until the next attempt replaces it.
 */
export function LoginScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const searchParams = useSearchParams()
  const { signInWithEmail, signInWithGoogle } = useAuthActions()
  const oauthProviders = useOAuthProviders()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(() =>
    searchParams.get('error') === OAUTH_CALLBACK_FAILED ? t('oauth_callback_failed') : null,
  )
  const [isLoading, setIsLoading] = useState(false)
  const [isGoogleLoading, setIsGoogleLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)
    try {
      await signInWithEmail(email, password)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('login_error'))
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleSignIn = async () => {
    setError(null)
    setIsGoogleLoading(true)
    try {
      await signInWithGoogle()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('login_error'))
      setIsGoogleLoading(false)
    }
  }

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <AuthWordmark subtitle={t('login_subtitle')} />

        <SupabaseSetupNotice />

        <form
          onSubmit={handleSubmit}
          className="border-border bg-card space-y-4 rounded-2xl border p-6 shadow-xs"
        >
          <h2 className="text-foreground text-lg font-semibold">{t('login_title')}</h2>

          {error && (
            <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm">
              {error}
            </div>
          )}

          {oauthProviders.google && (
            <>
              <button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={isLoading || isGoogleLoading}
                className="border-input text-foreground hover:bg-muted w-full rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isGoogleLoading ? t('google_signing_in') : t('google')}
              </button>

              <div className="text-muted-foreground flex items-center gap-3 text-xs tracking-wide uppercase">
                <span className="bg-border h-px flex-1" />
                <span>{t('or')}</span>
                <span className="bg-border h-px flex-1" />
              </div>
            </>
          )}

          <div>
            <label htmlFor="login-email" className="text-foreground mb-1 block text-sm font-medium">
              {t('email')}
            </label>
            <input
              id="login-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <div>
            <label
              htmlFor="login-password"
              className="text-foreground mb-1 block text-sm font-medium"
            >
              {t('password')}
            </label>
            <input
              id="login-password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
            {/* Spec § 7.1a: a ghost text action, right-aligned under the password field, with
                T-03's 44px target. */}
            <div className="flex justify-end">
              <Link href={`/${locale}/forgot-password`} className={SECONDARY_LINK}>
                {t('forgot_password_link')}
              </Link>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="bg-primary text-primary-foreground hover:bg-primary-hover w-full rounded-lg py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? t('signing_in') : t('sign_in')}
          </button>

          <p className="text-muted-foreground text-center text-xs">
            {t('no_account')}{' '}
            <Link href={`/${locale}/register`} className="text-primary hover:underline">
              {t('register_link')}
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
