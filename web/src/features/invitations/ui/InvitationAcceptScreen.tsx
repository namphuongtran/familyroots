'use client'

/**
 * The page an invitation link lands on (seed S-084).
 *
 * **Why this screen exists.** The admin's invitation carries a token, and until
 * now the only thing that took one was `POST /api/v1/invitations/{token}/accept`
 * — a `POST`-only route (`docs/contracts/rest-invitations-api.md:64`). Opening it
 * in a browser is a `GET`, so a relative who clicked the link they were sent saw an
 * error instead of an invitation. This is the door.
 *
 * **The accept is behind a button, not on render.** See the header of
 * `../hooks/use-accept-invitation` for why: accept grants a role and writes an
 * audit event, and a render-time call would fire on a prefetch, a strict-mode
 * double render, and every reload.
 *
 * **The email-match rule is the backend's and is not softened here.** Accept
 * refuses unless the signed-in user's email matches the invited email, case
 * insensitively (`docs/contracts/rest-invitations-api.md:66-68`,
 * `backend/app/domain/invitation/entity.py:121-122`). This screen has no idea which
 * email was invited — it is not in any response the invitee can read — so it cannot
 * pre-empt, work around, or explain away that check. It asks, and it renders the
 * refusal.
 *
 * **The token stays on this page.** `ui/InvitationAcceptPage`'s route
 * (`app/[locale]/(auth)/invitations/[token]/page.tsx`) declares
 * `referrer: 'no-referrer'`, `@/shared/telemetry/redact` keeps the token out of the
 * log, the Web Vitals report and Sentry, and nothing here writes it to a cookie, to
 * `sessionStorage`, or to a query string. That last one is a decision with a cost,
 * recorded on `signedOutHint` below.
 */

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import {
  Ban,
  CircleCheck,
  ClockAlert,
  Link2Off,
  LogIn,
  MailCheck,
  MailX,
  TriangleAlert,
  UserCheck,
  type LucideIcon,
} from 'lucide-react'
import { ApiError } from '@/shared/http/errors'
import { asClanRole, refusalFor, type InvitationRefusal } from '@/domain/invitation/invitation'
import { useAcceptInvitation } from '../hooks/use-accept-invitation'
import { useInvitationRequestContext } from './use-invitation-request-context'

export interface InvitationAcceptScreenProps {
  /** The opaque token from the URL. Passed down, never logged, never stored. */
  token: string
  /** The route locale, for the links out of this screen. */
  locale: string
}

/** What each refusal shows. One row per member of `InvitationRefusal`, exhaustively. */
interface RefusalPanel {
  icon: LucideIcon
  /** Message key under the `invitation` namespace. */
  heading: string
  body: string
  /** The way out. `T-17`: no state on this screen is a dead end. */
  action: 'sign-in' | 'select-clan' | 'retry'
}

/**
 * `Record<InvitationRefusal, …>` and not a partial map with a fallback: adding a
 * member to `InvitationRefusal` without adding its copy here fails
 * `pnpm type-check`, rather than silently rendering a blank panel.
 */
const PANELS: Readonly<Record<InvitationRefusal, RefusalPanel>> = {
  'email-mismatch': {
    icon: MailX,
    heading: 'email_mismatch_heading',
    body: 'email_mismatch_body',
    action: 'sign-in',
  },
  expired: {
    icon: ClockAlert,
    heading: 'expired_heading',
    body: 'expired_body',
    action: 'sign-in',
  },
  'no-longer-open': {
    icon: Ban,
    heading: 'no_longer_open_heading',
    body: 'no_longer_open_body',
    action: 'sign-in',
  },
  'already-member': {
    icon: UserCheck,
    heading: 'already_member_heading',
    body: 'already_member_body',
    // `docs/contracts/error-codes.md:147` names the client action for this code:
    // "Route into the clan". The clan picker is how this app does that.
    action: 'select-clan',
  },
  'not-found': {
    icon: Link2Off,
    heading: 'not_found_heading',
    body: 'not_found_body',
    action: 'sign-in',
  },
  'sign-in-required': {
    icon: LogIn,
    heading: 'sign_in_required_heading',
    body: 'sign_in_required_body',
    action: 'sign-in',
  },
  unavailable: {
    icon: TriangleAlert,
    heading: 'unavailable_heading',
    body: 'unavailable_body',
    action: 'retry',
  },
}

const PRIMARY_BUTTON =
  'bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring w-full max-w-xs rounded-full px-4 py-2.5 text-center text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:opacity-60'

export function InvitationAcceptScreen({ token, locale }: InvitationAcceptScreenProps) {
  const t = useTranslations('invitation')
  const { context, ready } = useInvitationRequestContext()
  const accept = useAcceptInvitation({ token, context })

  /**
   * The signed-out case, caught before the button rather than after a 401.
   *
   * `docs/contracts/rest-invitations-api.md:62-64` marks the accept row `Auth |
   * Yes`, and `backend/app/api/v1/invitations.py:96` depends on
   * `get_current_user`, reading `current_user["sub"]` and `current_user["email"]`
   * at `:104-105`. So the token alone accepts nothing: there has to be a session,
   * and its email has to match. Offering an Accept button to a signed-out visitor
   * would be offering a button whose only possible answer is 401.
   *
   * The 401 branch below is kept as well, and is not redundant: an access token
   * that expired while this page sat open is signed *in* by this check and refused
   * by the backend.
   */
  const signedOut = ready && context.accessToken === null

  const refusal: InvitationRefusal | null = signedOut
    ? 'sign-in-required'
    : accept.isError
      ? refusalFor(
          accept.error instanceof ApiError
            ? { code: accept.error.code, status: accept.error.status }
            : // A `NetworkError`, a `MalformedResponseError`, or a zod failure: no
              // code and no status, so `refusalFor` lands on `unavailable`. Passing
              // an empty code rather than inventing one keeps the mapping in one
              // place, in the domain, where it is tested without a browser.
              { code: '', status: 0 },
        )
      : null

  const granted = accept.data
  const grantedRole = granted ? asClanRole(granted.role) : null

  return (
    <div className="bg-background flex min-h-screen items-center justify-center px-4 py-12">
      {/*
        `max-w-md` and no fixed height anywhere: `T-05` (a translated string is
        taller in Vietnamese with full diacritics) and `T-04` (320dp at 200% text
        scale) are both release gates, per `.claude/rules/tailwind.md` § 7. Nothing
        on this screen is an unbreakable word — the product wordmark is deliberately
        not rendered here, which is what made `/vi/login` and `/vi/register` scroll
        sideways until seed S-034 added a `<wbr />` to each.
      */}
      <div className="w-full max-w-md space-y-6 text-center">
        {/*
          One live region for the whole outcome. The panel replaces itself in place
          after a button press, and a screen-reader user who cannot see that has to
          be told. `polite` and not `assertive`: it follows their own action, so it
          is not an interruption.
        */}
        <div aria-live="polite" className="space-y-6">
          {granted ? (
            <Panel icon={CircleCheck} tone="success" heading={t('accepted_heading')}>
              <p className="text-muted-foreground text-sm">{t('accepted_body')}</p>
              {grantedRole !== null && (
                <p className="text-foreground text-sm font-medium">
                  {t('accepted_role', { role: t(`role_${grantedRole}`) })}
                </p>
              )}
              <Link href={`/${locale}/select-clan`} className={PRIMARY_BUTTON}>
                {t('continue_button')}
              </Link>
            </Panel>
          ) : refusal !== null ? (
            <RefusalView
              refusal={refusal}
              locale={locale}
              onRetry={() => accept.mutate()}
              retrying={accept.isPending}
              t={t}
            />
          ) : (
            <Panel icon={MailCheck} tone="primary" heading={t('heading')}>
              <p className="text-muted-foreground text-sm">{t('body')}</p>
              <button
                type="button"
                className={PRIMARY_BUTTON}
                disabled={!ready || accept.isPending}
                onClick={() => accept.mutate()}
              >
                {accept.isPending ? t('accepting') : ready ? t('accept_button') : t('loading')}
              </button>
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}

function RefusalView({
  refusal,
  locale,
  onRetry,
  retrying,
  t,
}: {
  refusal: InvitationRefusal
  locale: string
  onRetry: () => void
  retrying: boolean
  t: (key: string) => string
}) {
  const panel = PANELS[refusal]

  return (
    <Panel icon={panel.icon} tone="destructive" heading={t(panel.heading)}>
      <p className="text-muted-foreground text-sm">{t(panel.body)}</p>
      {panel.action === 'retry' ? (
        <button type="button" className={PRIMARY_BUTTON} disabled={retrying} onClick={onRetry}>
          {retrying ? t('accepting') : t('retry_button')}
        </button>
      ) : panel.action === 'select-clan' ? (
        <Link href={`/${locale}/select-clan`} className={PRIMARY_BUTTON}>
          {t('continue_button')}
        </Link>
      ) : (
        <Link href={`/${locale}/login`} className={PRIMARY_BUTTON}>
          {t('sign_in_button')}
        </Link>
      )}
    </Panel>
  )
}

/**
 * `T-06`: colour is never the only channel. Every state below carries an icon and
 * its own heading text, so the three tones are reinforcement, not information.
 */
function Panel({
  icon: Icon,
  tone,
  heading,
  children,
}: {
  icon: LucideIcon
  tone: 'primary' | 'success' | 'destructive'
  heading: string
  children: React.ReactNode
}) {
  const iconTone =
    tone === 'success'
      ? 'text-success'
      : tone === 'destructive'
        ? 'text-destructive'
        : 'text-primary'

  return (
    <>
      <Icon className={`mx-auto h-12 w-12 ${iconTone}`} aria-hidden="true" />
      <h1 className="text-foreground font-serif text-2xl">{heading}</h1>
      <div className="flex flex-col items-center gap-4">{children}</div>
    </>
  )
}
