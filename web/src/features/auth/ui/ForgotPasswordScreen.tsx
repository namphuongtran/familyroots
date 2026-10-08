'use client'

/**
 * `/{locale}/forgot-password` (#201), reached from the sign-in screen's **Quên mật khẩu?** and from
 * the reset page's expired state. It asks for an address and sends `POST /auth/forgot-password`.
 *
 * **One message for every 200** (ADR-021): the screen never says whether the address has an
 * account, and shows its own message rather than the server's. A 429 shows the rate-limit message.
 * The form stays, so a person who mistyped the address can send again.
 *
 * Spec § 7 has no entry for this screen, so it follows the sign-in screen's layout.
 */
import { useState } from 'react'
import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { useRequestPasswordReset } from '../hooks/use-request-password-reset'
import { PRIMARY_ACTION, SECONDARY_LINK } from './auth-action-classes'
import { AuthWordmark } from './AuthWordmark'

export function ForgotPasswordScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const { state, request } = useRequestPasswordReset()
  const [email, setEmail] = useState('')
  const sending = state === 'sending'

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <AuthWordmark />

        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (!sending) request(email.trim())
          }}
          className="border-border bg-card space-y-4 rounded-2xl border p-6 shadow-xs"
        >
          <div className="space-y-1">
            <h2 className="text-foreground text-lg font-semibold">
              {t('forgot_password_heading')}
            </h2>
            <p className="text-muted-foreground text-sm">{t('forgot_password_body')}</p>
          </div>

          {state === 'sent' && (
            <p
              role="status"
              className="bg-success-container text-success-container-foreground rounded-md px-3 py-2 text-sm"
            >
              {t('forgot_password_sent')}
            </p>
          )}
          {(state === 'rate-limited' || state === 'failed') && (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
            >
              {state === 'rate-limited'
                ? t('forgot_password_rate_limited')
                : t('forgot_password_error')}
            </p>
          )}

          <div>
            <label
              htmlFor="forgot-password-email"
              className="text-foreground mb-1 block text-sm font-medium"
            >
              {t('email')}
            </label>
            {/* Read-only while sending, not disabled (spec § 7.1a). */}
            <input
              id="forgot-password-email"
              type="email"
              required
              autoComplete="email"
              readOnly={sending}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>

          <button type="submit" disabled={sending} className={PRIMARY_ACTION}>
            {sending ? t('verify_email_resend_sending') : t('forgot_password_submit')}
          </button>
        </form>

        <div className="text-center">
          <Link href={`/${locale}/login`} className={SECONDARY_LINK}>
            {t('verify_email_back_to_login')}
          </Link>
        </div>
      </div>
    </div>
  )
}
