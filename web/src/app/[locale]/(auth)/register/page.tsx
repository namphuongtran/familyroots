'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { SupabaseSetupNotice } from '@/components/auth/SupabaseSetupNotice'
import { useAuth, useAuthActions } from '@/lib/hooks/useAuth'

export default function RegisterPage() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { signUp, signInWithGoogle, completeOnboarding } = useAuthActions()
  const {
    user,
    isLoading: isAuthLoading,
    isAuthenticated,
    isPendingApproval,
    needsOnboarding,
  } = useAuth()
  // null = untouched, so the OAuth profile can supply the initial value.
  const [fullNameInput, setFullName] = useState<string | null>(null)
  const [emailInput, setEmail] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [clanAction, setClanAction] = useState<'join' | 'create'>('join')
  const [clanId, setClanId] = useState('')
  const [clanName, setClanName] = useState('')
  const [clanSlug, setClanSlug] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isGoogleLoading, setIsGoogleLoading] = useState(false)
  const isOAuthMode = searchParams.get('mode') === 'oauth' && isAuthenticated

  // Prefill from the OAuth profile by deriving during render rather than pushing
  // state from an effect: that is what eslint's react-hooks/set-state-in-effect
  // (new in eslint-config-next 16.2) flags, and it drops a cascading render.
  // Using ?? rather than the old || also means clearing a prefilled field now
  // sticks, instead of being refilled the next time `user` changes identity.
  const oauthProfile = isOAuthMode ? user : null
  const fullName = fullNameInput ?? oauthProfile?.full_name ?? ''
  const email = emailInput ?? oauthProfile?.email ?? ''

  useEffect(() => {
    if (isAuthLoading) {
      return
    }

    if (isAuthenticated && isPendingApproval) {
      router.replace(`/${locale}/pending-approval`)
      return
    }

    if (isAuthenticated && !needsOnboarding) {
      router.replace(`/${locale}/dashboard`)
    }
  }, [isAuthLoading, isAuthenticated, isPendingApproval, locale, needsOnboarding, router])

  const handleGoogleSignIn = async () => {
    setError(null)
    setIsGoogleLoading(true)
    try {
      await signInWithGoogle()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('register_error'))
      setIsGoogleLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)
    try {
      if (isOAuthMode) {
        await completeOnboarding({
          full_name: fullName,
          clan_action: clanAction,
          clan_id: clanAction === 'join' ? clanId : undefined,
          clan_name: clanAction === 'create' ? clanName : undefined,
          clan_slug: clanAction === 'create' ? clanSlug : undefined,
        })
      } else {
        const result = await signUp({
          email,
          password,
          full_name: fullName,
          clan_action: clanAction,
          clan_id: clanAction === 'join' ? clanId : undefined,
          clan_name: clanAction === 'create' ? clanName : undefined,
          clan_slug: clanAction === 'create' ? clanSlug : undefined,
        })
        setSuccess(result.message)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('register_error'))
    } finally {
      setIsLoading(false)
    }
  }

  if (success) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center px-4">
        <div className="border-border bg-card w-full max-w-sm rounded-2xl border p-8 text-center shadow-xs">
          <div className="mb-3 text-4xl">OK</div>
          <h2 className="text-foreground mb-2 font-serif text-xl">{t('register_title')}</h2>
          <p className="text-muted-foreground text-sm">{success}</p>
          <Link
            href={`/${locale}/login`}
            className="text-primary mt-4 inline-flex text-sm hover:underline"
          >
            {t('login_link')}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          {/* `<wbr />` is load-bearing — see the note on the login page (T-04, seed S-034). */}
          <h1 className="text-primary font-serif text-3xl">
            Family
            <wbr />
            Roots
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">{t('register_subtitle')}</p>
        </div>

        <SupabaseSetupNotice />

        <form
          onSubmit={handleSubmit}
          className="border-border bg-card space-y-4 rounded-2xl border p-6 shadow-xs"
        >
          <h2 className="text-foreground text-lg font-semibold">
            {isOAuthMode ? t('oauth_onboarding_title') : t('register_title')}
          </h2>
          {isOAuthMode && (
            <p className="text-muted-foreground text-sm">{t('oauth_onboarding_subtitle')}</p>
          )}

          {error && (
            <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm">
              {error}
            </div>
          )}

          {!isOAuthMode && (
            <>
              <button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={isLoading || isGoogleLoading}
                className="border-input text-foreground hover:bg-muted w-full rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isGoogleLoading ? t('google_signing_in') : t('google_register')}
              </button>

              <div className="text-muted-foreground flex items-center gap-3 text-xs tracking-wide uppercase">
                <span className="bg-border h-px flex-1" />
                <span>{t('or')}</span>
                <span className="bg-border h-px flex-1" />
              </div>
            </>
          )}

          <div>
            <label className="text-foreground mb-1 block text-sm font-medium">
              {t('full_name')}
            </label>
            <input
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <div>
            <label className="text-foreground mb-1 block text-sm font-medium">{t('email')}</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isOAuthMode}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          {!isOAuthMode && (
            <div>
              <label className="text-foreground mb-1 block text-sm font-medium">
                {t('password')}
              </label>
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
              />
            </div>
          )}

          <div className="space-y-2">
            <p className="text-foreground block text-sm font-medium">{t('register_subtitle')}</p>
            <label className="text-foreground flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="clanAction"
                checked={clanAction === 'join'}
                onChange={() => setClanAction('join')}
              />
              {t('join_clan')}
            </label>
            <label className="text-foreground flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="clanAction"
                checked={clanAction === 'create'}
                onChange={() => setClanAction('create')}
              />
              {t('create_clan')}
            </label>
          </div>

          {clanAction === 'join' ? (
            <div>
              <label className="text-foreground mb-1 block text-sm font-medium">
                {t('clan_slug')}
              </label>
              <input
                required
                value={clanId}
                onChange={(e) => setClanId(e.target.value)}
                placeholder="UUID"
                className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  {t('clan_name')}
                </label>
                <input
                  required
                  value={clanName}
                  onChange={(e) => setClanName(e.target.value)}
                  className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
                />
              </div>
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  {t('clan_slug')}
                </label>
                <input
                  required
                  value={clanSlug}
                  onChange={(e) => setClanSlug(e.target.value)}
                  className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
                />
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="bg-primary text-primary-foreground hover:bg-primary-hover w-full rounded-lg py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading
              ? isOAuthMode
                ? t('onboarding_submitting')
                : t('registering')
              : isOAuthMode
                ? t('complete_onboarding')
                : t('register')}
          </button>

          <p className="text-muted-foreground text-center text-xs">
            {isOAuthMode ? (
              t('oauth_onboarding_hint')
            ) : (
              <>
                {t('have_account')}{' '}
                <Link href={`/${locale}/login`} className="text-primary hover:underline">
                  {t('login_link')}
                </Link>
              </>
            )}
          </p>
        </form>
      </div>
    </div>
  )
}
