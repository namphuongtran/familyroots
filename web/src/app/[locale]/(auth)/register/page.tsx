'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { SupabaseSetupNotice } from '@/components/auth/SupabaseSetupNotice'
import {
  CLAN_CODE_MAX_LENGTH,
  CLAN_CODE_TAKEN_ERROR_CODE,
  suggestAlternativeClanCode,
  suggestClanCode,
} from '@/domain/clan/clan-code'
import { useAuth, useAuthActions } from '@/lib/hooks/useAuth'
import { cn } from '@/lib/utils/cn'

/**
 * The clan-create half of this screen reads a field-level error code, so it needs the
 * `code` out of the error envelope rather than the `message` — the standing rule from
 * `docs/contracts/error-codes.md`, restated in `src/shared/http/errors.ts`.
 *
 * `authProfileRepository.register`/`.onboard` still go through the legacy axios client
 * (`src/lib/api/axios.ts`), which rejects with the raw axios error, so the envelope sits
 * at `.response.data.error` rather than on an `ApiError`. `select-clan/page.tsx` reads the
 * same shape with a `backendErrorCode` twin of this function; the two collapse into one
 * helper when the legacy axios tree is deleted, which is not this seed's change.
 *
 * The `message` is returned alongside the code because the backend has already localised
 * it from `Accept-Language` (`backend/app/core/exceptions.py`'s `t(f"error.{code}")`).
 * It is displayed, never branched on.
 */
function backendError(cause: unknown): { code: string; message: string | null } | null {
  if (typeof cause !== 'object' || cause === null || !('response' in cause)) return null
  const response = (cause as { response?: unknown }).response
  if (typeof response !== 'object' || response === null || !('data' in response)) return null
  const data = (response as { data?: unknown }).data
  if (typeof data !== 'object' || data === null || !('error' in data)) return null
  const error = (data as { error?: unknown }).error
  if (typeof error !== 'object' || error === null || !('code' in error)) return null
  const { code, message } = error as { code?: unknown; message?: unknown }
  if (typeof code !== 'string') return null
  return { code, message: typeof message === 'string' && message ? message : null }
}

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
  // null = untouched, so the clan name can keep supplying the suggestion. Same shape,
  // and the same reason, as `fullNameInput`/`emailInput` above.
  const [clanSlugInput, setClanSlug] = useState<string | null>(null)
  const [clanSlugTaken, setClanSlugTaken] = useState<{
    message: string
    suggestion: string
  } | null>(null)
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
  // Spec § 7.1b: the clan code is "auto-suggested, slugified live from the name,
  // editable". Deriving it during render is what makes all three of those true at once
  // and needs no effect: while `clanSlugInput` is null every keystroke in the name field
  // re-renders a fresh suggestion, and the first keystroke in the code field makes it a
  // string, after which the name no longer reaches it. Clearing the code field leaves
  // `''`, not null, so an emptied code stays empty instead of being refilled.
  const clanSlug = clanSlugInput ?? suggestClanCode(clanName)

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
    setClanSlugTaken(null)
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
      const envelope = backendError(err)
      if (envelope?.code === CLAN_CODE_TAKEN_ERROR_CODE) {
        // Spec § 7.1b asks for this one inline on the code field, with a suggested
        // alternative — not as the page-level banner every other failure gets.
        setClanSlugTaken({
          message: envelope.message ?? t('clan_slug_taken'),
          suggestion: suggestAlternativeClanCode(clanSlug),
        })
        return
      }
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
                <label
                  htmlFor="clan-name"
                  className="text-foreground mb-1 block text-sm font-medium"
                >
                  {t('clan_name')}
                </label>
                <input
                  id="clan-name"
                  required
                  value={clanName}
                  onChange={(e) => setClanName(e.target.value)}
                  className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
                />
              </div>
              <div>
                <label
                  htmlFor="clan-slug"
                  className="text-foreground mb-1 block text-sm font-medium"
                >
                  {t('clan_slug')}
                </label>
                <input
                  id="clan-slug"
                  required
                  value={clanSlug}
                  onChange={(e) => setClanSlug(e.target.value)}
                  maxLength={CLAN_CODE_MAX_LENGTH}
                  // A code is an identifier, not prose: a phone keyboard must not
                  // capitalise it and a spell-checker must not underline it.
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  aria-invalid={clanSlugTaken ? true : undefined}
                  aria-describedby={
                    clanSlugTaken ? 'clan-slug-helper clan-slug-error' : 'clan-slug-helper'
                  }
                  className={cn(
                    'focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden',
                    // T-06: the border colour is a second channel, never the only one —
                    // the message and the `role="alert"` below carry the state in text.
                    // Tailwind 4.3.3 ships no `aria-invalid:` variant (0 hits in
                    // `node_modules/tailwindcss/dist/lib.js`, checked 2026-08-26), so the
                    // branch is here rather than in a class.
                    clanSlugTaken ? 'border-destructive' : 'border-input',
                  )}
                />
                <p id="clan-slug-helper" className="text-muted-foreground mt-1 text-xs">
                  {t('clan_slug_helper')}
                </p>
                {clanSlugTaken && (
                  <div id="clan-slug-error" role="alert" className="mt-1 space-y-1">
                    {/* `wrap-anywhere` rather than the default: a clan code can be up to
                        100 characters with no hyphen in it, which is one unbreakable word
                        and so a horizontal page scroll at 320px and 200% text scale
                        (T-04, the trap `.claude/rules/tailwind.md` § 7 records twice).
                        `overflow-wrap: anywhere` breaks inside the word only when the word
                        does not fit, so the prose around it still wraps normally. */}
                    <p className="text-destructive text-xs wrap-anywhere">
                      {clanSlugTaken.message}
                    </p>
                    {clanSlugTaken.suggestion && (
                      <button
                        type="button"
                        onClick={() => {
                          setClanSlug(clanSlugTaken.suggestion)
                          setClanSlugTaken(null)
                        }}
                        // min-h-11 is T-03's 44px touch target; the label wraps inside it.
                        className="border-input text-foreground hover:bg-muted inline-flex min-h-11 w-full items-center justify-center rounded-md border px-3 py-2 text-xs font-medium wrap-anywhere transition-colors"
                      >
                        {t('clan_slug_use_suggestion', { suggestion: clanSlugTaken.suggestion })}
                      </button>
                    )}
                  </div>
                )}
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
