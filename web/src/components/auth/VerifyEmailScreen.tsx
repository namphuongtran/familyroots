'use client'

/**
 * Spec §7.1c, surface 1 (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:882-898`):
 * the "blocked-at-login" screen for `403 email_not_verified` (`docs/contracts/error-codes.md`,
 * "Auth & session"). Surface 2 of §7.1c — the screen that lands from the email link itself — is
 * out of scope for S-026 (`docs/SEEDS.md`, "Out of scope": "Deep links from an email").
 *
 * **Why this screen has no real caller yet.** The only live sign-in path in this codebase,
 * `useAuth().signInWithEmail` (`src/lib/hooks/useAuth.ts`), calls
 * `authSessionPort.signInWithEmail` (`src/infrastructure/auth/supabase-auth-session-port.ts`),
 * which calls `supabase.auth.signInWithPassword` directly — it never reaches the backend's own
 * `POST /api/v1/auth/login`, which is the one endpoint that raises `email_not_verified`
 * (`docs/contracts/rest-auth-api.md`, "Email verification"). The backend-calling equivalent,
 * `authApi.login` in `src/lib/api/auth.ts`, is dead code today: `grep -rln "lib/api/auth'" src`
 * finds no importer. So this screen is reachable by direct navigation
 * (`/{locale}/verify-email?email=...`) and is fully tested against the real
 * `POST /auth/resend-verification` envelope, but nothing in this seed makes the login button
 * navigate here on a real 403 — that needs the sign-in path to call the backend endpoint that can
 * raise the code, which is a legacy-transport change reserved for a later seed, not a screen
 * change. Recorded here rather than silently wired around.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { MailCheck } from 'lucide-react'
import { apiFetch } from '@/shared/http/api-client'
import { getClientRequestContext } from '@/shared/http/context.client'
import { unwrapData } from '@/shared/http/envelope'

const RESEND_COOLDOWN_SECONDS = 60

/** `POST /auth/resend-verification` is a message envelope (`rest-auth-api.md`): `{"data": {"message": "..."}}`. */
function parseMessageEnvelope(raw: unknown): void {
  if (
    typeof raw !== 'object' ||
    raw === null ||
    typeof (raw as { message?: unknown }).message !== 'string'
  ) {
    throw new Error('resend-verification response missing "message"')
  }
}

type ResendStatus = 'idle' | 'sending' | 'sent' | 'error'

export function VerifyEmailScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const searchParams = useSearchParams()
  const email = searchParams.get('email')

  const [status, setStatus] = useState<ResendStatus>('idle')
  const [cooldown, setCooldown] = useState(0)

  // A plain countdown, not an announced one: spec §7.1a's identical cooldown on the
  // "resend registration email" button says the same thing — announce once, not every second.
  useEffect(() => {
    if (cooldown <= 0) return
    const id = setInterval(() => setCooldown((seconds) => Math.max(0, seconds - 1)), 1000)
    return () => clearInterval(id)
  }, [cooldown])

  async function handleResend() {
    if (!email) return
    setStatus('sending')
    try {
      const context = await getClientRequestContext()
      const body = await apiFetch('/auth/resend-verification', {
        context,
        method: 'POST',
        body: { email },
      })
      unwrapData(body, parseMessageEnvelope)
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
            {email ? t('verify_email_body_with_email', { email }) : t('verify_email_body_no_email')}
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

        <button
          type="button"
          onClick={handleResend}
          disabled={!canResend}
          className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring w-full rounded-full px-4 py-2.5 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status === 'sending'
            ? t('verify_email_resend_sending')
            : cooldown > 0
              ? t('verify_email_resend_cooldown', { seconds: cooldown })
              : t('verify_email_resend_button')}
        </button>

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
