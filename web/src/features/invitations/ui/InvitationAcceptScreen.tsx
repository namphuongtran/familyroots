'use client'

/**
 * The page an invitation link lands on.
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
 * `sessionStorage`, to `localStorage`, or to a query string.
 *
 * **So the token is carried across no sign-in and no registration, and that is a decision with a
 * cost.** It was made in `d35decb` and extended to registration by #196. Every carry mechanism
 * puts a bearer credential in a second place: a query string lands it in browser history and in
 * later `Referer` headers, `sessionStorage` dies at the confirmation email's new tab or other
 * device, and `localStorage` keeps it at rest with nothing owning its lifetime. Carrying it through
 * the confirmation email would need a per-request redirect on a non-enumerating route. So the
 * signed-out state offers two ways on, sign in or create an account (`inviteeRegisterPath`, whose
 * marker carries no part of the token), and its copy says to open this link again afterwards. The
 * link is in the invitee's inbox or chat, re-opening it costs one tap, and the token appears only
 * where it must: this page's URL and the accept request's path.
 * `e2e/auth/invitee-registers.auth.spec.ts` walks it and records every URL.
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
import { inviteeRegisterPath } from '@/features/auth'
import { useClientRequestContext } from '@/shared/http/context.client'
import { ApiError } from '@/shared/http/errors'
import { asClanRole, refusalFor, type InvitationRefusal } from '@/domain/invitation/invitation'
import { useAcceptInvitation } from '../hooks/use-accept-invitation'

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
  /**
   * The way out. `T-17`: no state on this screen is a dead end. `sign-in-or-register` is the
   * signed-out state's: a visitor with no account has to be able to make one (#196).
   */
  action: 'sign-in' | 'sign-in-or-register' | 'select-clan' | 'retry'
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
    action: 'sign-in-or-register',
  },
  unavailable: {
    icon: TriangleAlert,
    heading: 'unavailable_heading',
    body: 'unavailable_body',
    action: 'retry',
  },
}

/**
 * `min-h-11` is T-03's 44px touch target, which `py-2.5` alone missed by 4px. `inline-flex` centres
 * the label when one of these is a link, whose box does not centre its text the way a button does.
 */
const PRIMARY_BUTTON =
  'bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring inline-flex min-h-11 w-full max-w-xs items-center justify-center rounded-full px-4 py-2.5 text-center text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:opacity-60'

/** The second way on, beside a primary one. `border-input` is the control boundary that clears 3:1. */
const SECONDARY_BUTTON =
  'border-input text-foreground hover:bg-muted focus:ring-ring inline-flex min-h-11 w-full max-w-xs items-center justify-center rounded-full border px-4 py-2.5 text-center text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden'

export function InvitationAcceptScreen({ token, locale }: InvitationAcceptScreenProps) {
  const t = useTranslations('invitation')
  /**
   * **No `X-Current-Clan-Id`, and that is the contract's rule rather than a shortcut.**
   * `docs/contracts/rest-invitations-api.md:72-74`: "The invitee surface takes no
   * `X-Current-Clan-Id`, and cannot. The invitee is not a member of the clan yet, so there is no
   * clan for them to select." A stale `current_clan_id` cookie from an earlier session would
   * otherwise put a header on this request that means nothing here, so `clanScoped: false` leaves
   * it off the context and off the context a refresh resolves.
   *
   * `ready` keeps the Accept button disabled until the session has been read, rather than firing a
   * call with no `Authorization` header and turning a signed-in user into a spurious 401.
   */
  const { context, ready, refreshAuth } = useClientRequestContext({ clanScoped: false })
  const accept = useAcceptInvitation({ token, context, refreshAuth })

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
   * The 401 branch below is kept as well, and is not redundant. An access token that
   * expired while this page sat open is refreshed and the accept retried, through
   * `refreshAuth`, but a session Supabase will no longer refresh still ends in a 401.
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
        sideways until the text-scale spec added a `<wbr />` to each.
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
  // The register screen's own title, so the link reads the same as the page it opens.
  const tAuth = useTranslations('auth')

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
      {panel.action === 'sign-in-or-register' && (
        <>
          <p className="text-muted-foreground text-sm">{t('no_account_body')}</p>
          <Link href={inviteeRegisterPath(locale)} className={SECONDARY_BUTTON}>
            {tAuth('register_title')}
          </Link>
        </>
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
