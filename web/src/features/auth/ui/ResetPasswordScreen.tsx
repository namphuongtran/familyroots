'use client'

/**
 * The landing from the password-reset email, `/{locale}/reset-password?token_hash=…&type=recovery`
 * (#201, ADR-063). Spec § 7 defers this screen's detail (`design-system-and-screens.md:2441`), so
 * the form follows the sign-in screen's layout and the outcomes follow the confirmation landing's
 * (`VerifyEmailConfirmScreen`, #200).
 *
 * **The new-password form shows at once, and loading the page spends nothing** (ADR-063 § 2). An
 * email scanner fetches the link and submits no form. One submit verifies the token and then sets
 * the password; a retry after a refused password sets it only (`useResetPassword`).
 *
 * **Success keeps the session** (§ 3), and **Tiếp tục** goes to `/{locale}/dashboard`, the entry
 * the server guard routes from (ADR-061 § 3). **Expired**, for a refused verify and for a link this
 * page cannot spend, links to `/{locale}/forgot-password` to ask for a new one.
 */
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { useResetPassword } from '../hooks/use-reset-password'
import { emailLinkTokenHash } from '../model/email-link'
import { type PasswordRefusal } from '../model/password-recovery'
import { PRIMARY_ACTION, SECONDARY_LINK } from './auth-action-classes'
import { AuthOutcome } from './AuthOutcome'
import { AuthWordmark } from './AuthWordmark'

const REFUSAL_KEY = {
  weak: 'reset_password_weak',
  same: 'reset_password_same',
  other: 'reset_password_error',
} as const satisfies Record<PasswordRefusal, string>

export function ResetPasswordScreen() {
  const t = useTranslations('auth')
  const tMemberForm = useTranslations('member_form')
  const locale = useLocale()
  const tokenHash = emailLinkTokenHash(useSearchParams(), 'recovery')
  const { state, submit } = useResetPassword()
  const [password, setPassword] = useState('')
  const shown = tokenHash === null ? 'expired' : state.kind

  // A submit that ends the form moves focus to the heading of what replaced it, rather than
  // letting it fall to the body. A link that cannot be spent is read on load.
  const outcomeHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (state.kind === 'success' || state.kind === 'expired') outcomeHeading.current?.focus()
  }, [state.kind])

  if (shown === 'success') {
    return (
      <AuthOutcome
        tone="bg-success-container text-success-container-foreground"
        icon={<CircleCheck className="mx-auto h-12 w-12" aria-hidden="true" />}
        heading={t('reset_password_success_heading')}
        headingRef={outcomeHeading}
        body={t('reset_password_success_body')}
      >
        <Link href={`/${locale}/dashboard`} className={PRIMARY_ACTION}>
          {tMemberForm('continue_label')}
        </Link>
      </AuthOutcome>
    )
  }

  if (shown === 'expired') {
    return (
      <AuthOutcome
        tone="bg-warning-container text-warning-container-foreground"
        icon={<CircleAlert className="mx-auto h-12 w-12" aria-hidden="true" />}
        heading={t('verify_confirm_expired_heading')}
        headingRef={outcomeHeading}
        body={t('reset_password_expired_body')}
      >
        <Link href={`/${locale}/forgot-password`} className={PRIMARY_ACTION}>
          {t('reset_password_request_new')}
        </Link>
        <Link href={`/${locale}/login`} className={SECONDARY_LINK}>
          {t('verify_email_back_to_login')}
        </Link>
      </AuthOutcome>
    )
  }

  const saving = state.kind === 'saving'
  const refusal = state.kind === 'ready' ? state.refusal : null

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <AuthWordmark />

        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (tokenHash !== null) submit(tokenHash, password)
          }}
          className="border-border bg-card space-y-4 rounded-2xl border p-6 shadow-xs"
        >
          <div className="space-y-1">
            <h2 className="text-foreground text-lg font-semibold">{t('reset_password_heading')}</h2>
            <p className="text-muted-foreground text-sm">{t('reset_password_body')}</p>
          </div>

          {refusal && (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
            >
              {t(REFUSAL_KEY[refusal])}
            </p>
          )}

          <div>
            <label
              htmlFor="reset-password-new"
              className="text-foreground mb-1 block text-sm font-medium"
            >
              {t('reset_password_new_password')}
            </label>
            {/* Read-only while saving, not disabled: a disabled field loses its value
                announcement (spec § 7.1a). */}
            <input
              id="reset-password-new"
              type="password"
              required
              autoComplete="new-password"
              readOnly={saving}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <button type="submit" disabled={saving} className={PRIMARY_ACTION}>
            {saving ? tMemberForm('saving') : t('reset_password_submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
