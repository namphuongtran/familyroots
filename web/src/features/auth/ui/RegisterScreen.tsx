'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import {
  CLAN_CODE_MAX_LENGTH,
  CLAN_CODE_TAKEN_ERROR_CODE,
  CLAN_NOT_FOUND_ERROR_CODE,
  isValidClanCode,
  suggestAlternativeClanCode,
  suggestClanCode,
} from '@/domain/clan/clan-code'
import { cn } from '@/lib/utils/cn'
import { ApiError } from '@/shared/http/errors'
import { useAuthActions } from '../hooks/use-auth-actions'
import { useSession } from '../hooks/use-session'
import { isInviteeRegister } from '../model/invitee-register'
import { landingPath } from '../model/landing'
import { SupabaseSetupNotice } from './SupabaseSetupNotice'

/**
 * The register screen, and OAuth onboarding (`?mode=oauth`) on the same form.
 * `app/[locale]/(auth)/register/page.tsx` only routes here.
 *
 * **Reached from an invitation (`?from=invitation`, #196), the form asks for no clan.** It sends
 * `email`, `password` and `full_name` and nothing else, the body ADR-058 § 1 made the invitee's:
 * the membership arrives from accept, after the person confirms, signs in and opens the link
 * again. The marker carries no part of the token; `../model/invitee-register` says why. Reached
 * any other way, the join/create choice is unchanged. `RegisterScreen.invitee.test.tsx` reads the
 * body each way.
 *
 * Its form keeps the `register-` ids #195 gave it, so every input is still named by its visible
 * label. `register/page.test.tsx` and `register/page.success.test.tsx` read that, and the second
 * runs the real actions and repository against MSW (#182).
 *
 * The clan fields read a field-level error **code**, never the `message`
 * (`docs/contracts/error-codes.md`). Register and onboard go through `apiFetch` now, which
 * rejects with an `ApiError`, so the code is on the error itself. The `message` arrives already
 * localised from `Accept-Language` and is displayed, never branched on.
 */
export function RegisterScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { register, signInWithGoogle, completeOnboarding } = useAuthActions()
  const { session, access } = useSession()
  // null = untouched, so the OAuth profile can supply the initial value.
  const [fullNameInput, setFullName] = useState<string | null>(null)
  const [emailInput, setEmail] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [clanAction, setClanAction] = useState<'join' | 'create'>('join')
  const [clanCode, setClanCode] = useState('')
  // Which of the two field-level failures the join code has, or none. Spec § 7.1b puts
  // `clan_not_found` inline on this field rather than in the page-level banner; `invalid`
  // is the shape check below, which never leaves the browser.
  const [clanCodeError, setClanCodeError] = useState<'invalid' | 'not_found' | null>(null)
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
  const isOAuthMode = searchParams.get('mode') === 'oauth' && Boolean(session)
  const isInviteeMode = !isOAuthMode && isInviteeRegister(searchParams)

  // Prefill from the OAuth profile by deriving during render rather than pushing
  // state from an effect: that is what eslint's react-hooks/set-state-in-effect
  // (new in eslint-config-next 16.2) flags, and it drops a cascading render.
  // Using ?? rather than the old || also means clearing a prefilled field now
  // sticks, instead of being refilled the next time the session changes identity.
  const oauthProfile = isOAuthMode ? session?.profile : null
  const fullName = fullNameInput ?? oauthProfile?.fullName ?? ''
  const email = emailInput ?? oauthProfile?.email ?? ''
  // Spec § 7.1b: the clan code is "auto-suggested, slugified live from the name,
  // editable". Deriving it during render is what makes all three of those true at once
  // and needs no effect: while `clanSlugInput` is null every keystroke in the name field
  // re-renders a fresh suggestion, and the first keystroke in the code field makes it a
  // string, after which the name no longer reaches it. Clearing the code field leaves
  // `''`, not null, so an emptied code stays empty instead of being refilled.
  const clanSlug = clanSlugInput ?? suggestClanCode(clanName)

  // A signed-in user belongs here only to onboard. Everyone else signed in goes where their
  // access state says, through the same table sign-in uses.
  useEffect(() => {
    if (access === null || access.kind === 'signed-out' || access.kind === 'needs-onboarding') {
      return
    }
    router.replace(landingPath(access, locale))
  }, [access, locale, router])

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
    setClanCodeError(null)

    // Pasted codes arrive with whitespace far more often than people mistype them, and a
    // trailing space is the one "wrong shape" that is not the person's mistake.
    const joinCode = clanCode.trim()

    // The shape check runs before the request, not after it. ADR-057 § 2 makes a badly
    // shaped code a 422 `validation_error` naming `body.clan_code`
    // (`docs/contracts/rest-auth-api.md`'s "The join identifier" table), which has no copy
    // a person can read and would otherwise land in the page-level banner. `isValidClanCode`
    // is the clan-code spec's, compiled from the backend's own `_SLUG_PATTERN`, so this is not a second
    // validator for the same shape. No `pattern` attribute, because the browser's own
    // validation bubble is not localised and every string on this screen goes through
    // next-intl.
    if (!isInviteeMode && clanAction === 'join' && !isValidClanCode(joinCode)) {
      setClanCodeError('invalid')
      return
    }

    setIsLoading(true)
    try {
      if (isOAuthMode) {
        await completeOnboarding({
          full_name: fullName,
          clan_action: clanAction,
          clan_code: clanAction === 'join' ? joinCode : undefined,
          clan_name: clanAction === 'create' ? clanName : undefined,
          clan_slug: clanAction === 'create' ? clanSlug : undefined,
        })
      } else {
        // An invitee names no clan, so the body has no clan key at all. ADR-058 § 2 refuses a
        // clan field without `clan_action`, and `clan_action` without a clan is the join-code
        // error, so a key too many here stops the invitee at this step.
        const result = await register({
          email,
          password,
          full_name: fullName,
          ...(isInviteeMode
            ? {}
            : {
                clan_action: clanAction,
                clan_code: clanAction === 'join' ? joinCode : undefined,
                clan_name: clanAction === 'create' ? clanName : undefined,
                clan_slug: clanAction === 'create' ? clanSlug : undefined,
              }),
        })
        setSuccess(result.message)
      }
    } catch (err: unknown) {
      const apiError = err instanceof ApiError ? err : null
      if (apiError?.code === CLAN_NOT_FOUND_ERROR_CODE) {
        // Spec § 7.1b: inline on the code field, in this screen's own words. The backend
        // `message` is deliberately not used here — see `CLAN_NOT_FOUND_ERROR_CODE`.
        setClanCodeError('not_found')
        return
      }
      if (apiError?.code === CLAN_CODE_TAKEN_ERROR_CODE) {
        // Spec § 7.1b asks for this one inline on the code field, with a suggested
        // alternative — not as the page-level banner every other failure gets.
        setClanSlugTaken({
          message: apiError.message || t('clan_slug_taken'),
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
          {isInviteeMode && (
            <p className="text-muted-foreground mt-2 text-sm">
              {t('register_invitee_success_next')}
            </p>
          )}
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
          {/* `<wbr />` is load-bearing — see the note on the login page (T-04). */}
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
          {isInviteeMode && (
            <p className="text-muted-foreground text-sm">{t('register_invitee_hint')}</p>
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
            <label
              htmlFor="register-full-name"
              className="text-foreground mb-1 block text-sm font-medium"
            >
              {t('full_name')}
            </label>
            <input
              id="register-full-name"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <div>
            <label
              htmlFor="register-email"
              className="text-foreground mb-1 block text-sm font-medium"
            >
              {t('email')}
            </label>
            <input
              id="register-email"
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
              <label
                htmlFor="register-password"
                className="text-foreground mb-1 block text-sm font-medium"
              >
                {t('password')}
              </label>
              <input
                id="register-password"
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

          {!isInviteeMode && (
            <>
              <div className="space-y-2">
                <p className="text-foreground block text-sm font-medium">
                  {t('register_subtitle')}
                </p>
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
                  <label
                    htmlFor="clan-code"
                    className="text-foreground mb-1 block text-sm font-medium"
                  >
                    {t('clan_slug')}
                  </label>
                  <input
                    id="clan-code"
                    required
                    value={clanCode}
                    onChange={(e) => setClanCode(e.target.value)}
                    maxLength={CLAN_CODE_MAX_LENGTH}
                    // A code is an identifier, not prose — same reason as the create field.
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    aria-invalid={clanCodeError ? true : undefined}
                    aria-describedby={
                      clanCodeError ? 'clan-code-helper clan-code-error' : 'clan-code-helper'
                    }
                    className={cn(
                      'focus:ring-ring w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden',
                      // T-06: the border is the second channel, never the only one. The
                      // message below carries the state in text, inside a `role="alert"`.
                      clanCodeError ? 'border-destructive' : 'border-input',
                    )}
                  />
                  {/* **No `wrap-anywhere` here, and that is a measurement rather than an
                  oversight.** `.claude/rules/tailwind.md` § 7 records the unbreakable-word
                  overflow three times (the text-scale spec's wordmark, the banner spec's Supabase banner, the clan-code spec's
                  suggestion button), so this field was built expecting to be the fourth
                  and then measured at 320px and 200% root font size on 2026-08-26. It is
                  not. A hyphen is itself a break opportunity under `overflow-wrap: normal`,
                  so `nguyen-huu-thanh-oai` in the helper wraps on its own, and neither
                  message below interpolates the typed code. With the class and without it
                  the readings are identical: page 320/320, this paragraph 158/158, the
                  error paragraph 158/158, with only `overflowWrap` moving from `normal` to
                  `anywhere`. The clan-code spec's case is different because its button echoed a
                  100-character code back as text; the 100 characters here stay inside the
                  input, whose own 1604px scrollWidth does not widen the page.
                  `e2e/register-join-code.spec.ts` keeps the T-04 reading regardless. If a
                  later change puts the code inside one of these messages, the class comes
                  back and the reading will then discriminate. */}
                  <p id="clan-code-helper" className="text-muted-foreground mt-1 text-xs">
                    {t('clan_slug_join_helper')}
                  </p>
                  {clanCodeError && (
                    <p id="clan-code-error" role="alert" className="text-destructive mt-1 text-xs">
                      {clanCodeError === 'not_found'
                        ? t('clan_slug_not_found')
                        : t('clan_slug_invalid')}
                    </p>
                  )}
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
                            {t('clan_slug_use_suggestion', {
                              suggestion: clanSlugTaken.suggestion,
                            })}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
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
