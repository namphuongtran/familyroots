'use client'

/**
 * Spec §7.1c, surface 1 (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:882-898`):
 * the "blocked-at-login" screen for `403 email_not_verified` (`docs/contracts/error-codes.md`,
 * "Auth & session"). Surface 2 of §7.1c, the screen that lands from the email link itself, is
 * `VerifyEmailConfirmScreen` (#200).
 *
 * **How a real sign-in reaches it (#183, ADR-061 § 7).** Sign-in is Supabase-direct, so the
 * backend's `403 email_not_verified` is never raised on the way here. Supabase refuses a password
 * sign-in for an unconfirmed account with its own error code, `email_not_confirmed`, and
 * `useAuthActions().signInWithEmail` routes that to `/{locale}/verify-email?email=…`. Before #183
 * nothing did, and the screen was reachable only by typing its URL.
 *
 * **Reached with no `?email=`, it asks for the address (#200).** Surface 2's expired state,
 * `VerifyEmailConfirmScreen`, sends a person here to resend, and its `token_hash` names no
 * address. Before #200 the resend was disabled with no address, which left that person only the
 * way back to the login screen.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { MailCheck } from 'lucide-react'
import { authCallOptions } from '../hooks/auth-request-context'
import { resendVerification } from '../server/auth-repository'

const RESEND_COOLDOWN_SECONDS = 60

type ResendStatus = 'idle' | 'sending' | 'sent' | 'error'

export function VerifyEmailScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const searchParams = useSearchParams()
  const linkedEmail = searchParams.get('email') || null
  const [typedEmail, setTypedEmail] = useState('')
  const email = linkedEmail ?? (typedEmail.trim() || null)

  const [status, setStatus] = useState<ResendStatus>('idle')
  const [cooldown, setCooldown] = useState(0)

  // A plain countdown, not an announced one: spec §7.1a's identical cooldown on the
  // "resend registration email" button says the same thing — announce once, not every second.
  useEffect(() => {
    if (cooldown <= 0) return
    const id = setInterval(() => setCooldown((seconds) => Math.max(0, seconds - 1)), 1000)
    return () => clearInterval(id)
  }, [cooldown])

  async function handleResend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!email) return
    setStatus('sending')
    try {
      await resendVerification(email, await authCallOptions())
      setStatus('sent')
      setCooldown(RESEND_COOLDOWN_SECONDS)
    } catch {
      // `POST /auth/resend-verification` is 200-always and non-enumerating
      // (rest-auth-api.md) — the only failures reachable here are transport
      // failures (`NetworkError`) or a malformed body, never a "no such
      // email" rejection. Either way there is nothing more specific to say.
      setStatus('error')
    }
  }

  const canResend = Boolean(email) && status !== 'sending' && cooldown === 0

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div
          className="bg-heritage-container mx-auto flex h-16 w-16 items-center justify-center rounded-full"
          aria-hidden="true"
        >
          <MailCheck className="text-heritage-container-foreground h-8 w-8" />
        </div>

        <div className="space-y-2">
          <h1 className="text-foreground font-serif text-2xl">{t('verify_email_heading')}</h1>
          <p className="text-muted-foreground text-sm">
            {linkedEmail
              ? t('verify_email_body_with_email', { email: linkedEmail })
              : t('verify_email_body_no_email')}
          </p>
        </div>

        {status === 'sent' && (
          <p role="status" className="text-primary text-sm">
            {t('verify_email_resend_sent')}
          </p>
        )}
        {status === 'error' && (
          <p role="alert" className="text-destructive text-sm">
            {t('verify_email_resend_error')}
          </p>
        )}

        <form onSubmit={handleResend} className="space-y-4">
          {linkedEmail === null && (
            <div className="text-left">
              <label
                htmlFor="verify-email-address"
                className="text-foreground mb-1 block text-sm font-medium"
              >
                {t('email')}
              </label>
              <input
                id="verify-email-address"
                type="email"
                autoComplete="email"
                value={typedEmail}
                onChange={(e) => setTypedEmail(e.target.value)}
                className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={!canResend}
            className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring w-full rounded-full px-4 py-2.5 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:cursor-not-allowed disabled:opacity-50"
          >
            {status === 'sending'
              ? t('verify_email_resend_sending')
              : cooldown > 0
                ? t('verify_email_resend_cooldown', { seconds: cooldown })
                : t('verify_email_resend_button')}
          </button>
        </form>

        {/* Spec §7.1c's ghost "Đổi địa chỉ email" points at "support/admin contact", and no
            such surface exists in this app yet — there is no self-service email-change flow
            and no support-ticket screen. Rendered as plain text rather than a link to nowhere,
            which T-17 (never a dead end) reads as a false affordance if it were a button. */}
        <p className="text-muted-foreground text-xs">{t('verify_email_wrong_address_note')}</p>

        <Link
          href={`/${locale}/login`}
          className="text-primary inline-flex text-sm hover:underline"
        >
          {t('verify_email_back_to_login')}
        </Link>
      </div>
    </div>
  )
}
