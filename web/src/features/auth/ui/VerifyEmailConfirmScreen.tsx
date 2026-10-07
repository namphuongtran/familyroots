'use client'

/**
 * Spec §7.1c, surface 2 (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:888-898`):
 * the landing from the sign-up confirmation email, `/{locale}/verify-email/confirm?token_hash=…&type=email`
 * (#200, ADR-063). `VerifyEmailScreen` is surface 1, the blocked-at-login screen.
 *
 * **Four states.** Ready, a button. Verifying, a spinner and text, no skeleton. Success, which
 * keeps the session Supabase answered with (ADR-063 § 3) and goes on to `/{locale}/dashboard`,
 * the entry the server guard routes from (ADR-061 § 3): it sends a person to pending approval,
 * onboarding or the dashboard by their access state. Expired, for any failure and for a link
 * this page cannot spend, which offers the resend on `/{locale}/verify-email`.
 *
 * **Loading the page spends nothing** (ADR-063 § 2). An email scanner fetches the link, and it
 * does not press buttons, so only the press sends `POST /auth/v1/verify`.
 *
 * `success-container` is spec § 2.1's, added to `globals.css` by #200. Spec § 2.1's
 * `warning-container` does not exist there; `accent` is its stand-in, as on
 * `ClanSuspendedScreen`, whose header gives the reason.
 */
import { useEffect, useRef } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { CircleAlert, CircleCheck, LoaderCircle, MailCheck } from 'lucide-react'
import { useConfirmEmail } from '../hooks/use-confirm-email'
import { confirmationTokenHash } from '../model/email-confirmation'

const PRIMARY_ACTION =
  'bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring inline-flex w-full justify-center rounded-full px-4 py-2.5 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden'

export function VerifyEmailConfirmScreen() {
  const t = useTranslations('auth')
  const tMemberForm = useTranslations('member_form')
  const locale = useLocale()
  const tokenHash = confirmationTokenHash(useSearchParams())
  const { state, confirm } = useConfirmEmail()
  const shown = tokenHash === null ? 'expired' : state

  // The press removes the button, so focus moves to the heading of what replaced it rather than
  // falling to the body. Only after a press: a link that cannot be spent is read on load.
  const outcomeHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (state === 'success' || state === 'expired') outcomeHeading.current?.focus()
  }, [state])

  if (shown === 'success') {
    return (
      <Outcome
        className="bg-success-container text-success-container-foreground"
        icon={<CircleCheck className="mx-auto h-12 w-12" aria-hidden="true" />}
        heading={t('verify_confirm_success_heading')}
        headingRef={outcomeHeading}
        body={t('verify_confirm_success_body')}
      >
        <Link href={`/${locale}/dashboard`} className={PRIMARY_ACTION}>
          {tMemberForm('continue_label')}
        </Link>
      </Outcome>
    )
  }

  if (shown === 'expired') {
    return (
      <Outcome
        className="bg-accent text-accent-foreground"
        icon={<CircleAlert className="mx-auto h-12 w-12" aria-hidden="true" />}
        heading={t('verify_confirm_expired_heading')}
        headingRef={outcomeHeading}
        body={t('verify_confirm_expired_body')}
      >
        <Link href={`/${locale}/verify-email`} className={PRIMARY_ACTION}>
          {t('verify_email_resend_button')}
        </Link>
        <Link
          href={`/${locale}/login`}
          className="text-primary inline-flex text-sm hover:underline"
        >
          {t('verify_email_back_to_login')}
        </Link>
      </Outcome>
    )
  }

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
          <h1 className="text-foreground font-serif text-2xl">{t('verify_confirm_heading')}</h1>
          <p className="text-muted-foreground text-sm">{t('verify_confirm_body')}</p>
        </div>

        {shown === 'verifying' ? (
          <p
            role="status"
            className="text-muted-foreground flex items-center justify-center gap-2 py-2.5 text-sm"
          >
            <LoaderCircle className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
            {t('verify_confirm_verifying')}
          </p>
        ) : (
          <button
            type="button"
            onClick={() => {
              if (tokenHash !== null) confirm(tokenHash)
            }}
            className={PRIMARY_ACTION}
          >
            {t('verify_confirm_button')}
          </button>
        )}
      </div>
    </div>
  )
}

function Outcome({
  className,
  icon,
  heading,
  headingRef,
  body,
  children,
}: {
  className: string
  icon: React.ReactNode
  heading: string
  headingRef: React.RefObject<HTMLHeadingElement | null>
  body: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className={`space-y-4 rounded-2xl px-6 py-8 ${className}`}>
          {icon}
          <h1 ref={headingRef} tabIndex={-1} className="font-serif text-2xl focus:outline-hidden">
            {heading}
          </h1>
          <p className="text-sm">{body}</p>
        </div>
        <div className="flex flex-col items-center gap-3">{children}</div>
      </div>
    </div>
  )
}
