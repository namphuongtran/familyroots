'use client'

/**
 * Spec §7.2a (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:904-930`),
 * the screen for a signed-in user whose access state is `pending-approval`: a pending
 * membership and no approved one (`@/domain/session/access-state`). That is the same fact the
 * backend's `no_approved_clan_membership` 403 guards on clan-scoped routes
 * (`docs/contracts/frontend-integration-guide.md` §1.2/§5). The "no membership at all"
 * onboarding variant the spec puts in the same screen is a separate route here: the
 * `needs-onboarding` state lands on `/register?mode=oauth`, which already has the join/create
 * segmented control (spec §7.1b), so this screen sends the user there rather than rebuilding it.
 *
 * **It never names the clan, because nothing can tell it which clan.** `GET /auth/me` and
 * `GET /me/clans` both read approved memberships only (`rest-auth-api.md` §1.1,
 * `frontend-integration-guide.md` §1.2), so neither returns the name of a clan the user is only
 * pending in. `POST /auth/login`'s `user.clan_name` does carry it, but sign-in is
 * Supabase-direct (ADR-061 § 7) and never calls that endpoint. The legacy screen read a
 * `clan_name` that was empty for every user who could reach it, so its with-name sentence was
 * never shown. `pending_screen_body_with_clan` stays in the message files for the day a source
 * exists.
 *
 * **It does not promise a notification on approval, unlike the spec's literal copy**
 * ("Chúng tôi sẽ gửi thông báo ngay khi bạn được duyệt", design spec line 915-916). No
 * notification pipeline fires on membership approval today, so promising one would be a false
 * statement to the user. Where this comment and the older spec prose disagree, this comment is
 * the current decision.
 *
 * **"Check again" refetches the session.** It used to read `GET /auth/me` by hand and then ask
 * the legacy store to resync. Now the refetched session is the one every consumer reads, so if
 * the membership was approved the access state changes, and the redirect below takes the user
 * where it says.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { CheckCircle2, Circle, Clock } from 'lucide-react'
import { accessStateOf } from '@/domain/session/access-state'
import { readCurrentClanId } from '@/shared/http/context.client'
import { useAuthActions } from '../hooks/use-auth-actions'
import { useSession } from '../hooks/use-session'
import { landingPath } from '../model/landing'

type RecheckStatus = 'idle' | 'checking' | 'still-pending' | 'error'

export function PendingApprovalScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const { access, refetch } = useSession()
  const { signOut } = useAuthActions()
  const [recheckStatus, setRecheckStatus] = useState<RecheckStatus>('idle')

  useEffect(() => {
    if (access !== null && access.kind !== 'pending-approval') {
      router.replace(landingPath(access, locale))
    }
  }, [access, locale, router])

  async function handleRecheck() {
    setRecheckStatus('checking')
    try {
      const session = await refetch()
      if (session === undefined) {
        setRecheckStatus('error')
        return
      }
      const next = accessStateOf(session, readCurrentClanId())
      // Anything but pending: the effect above is already taking the user where it says.
      setRecheckStatus(next.kind === 'pending-approval' ? 'still-pending' : 'idle')
    } catch {
      setRecheckStatus('error')
    }
  }

  if (access === null) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center px-4">
        <p className="text-muted-foreground text-sm">{t('loading')}</p>
      </div>
    )
  }

  if (access.kind !== 'pending-approval') {
    // Mid-redirect (the effect above already fired). Render nothing rather
    // than a flash of this screen's content.
    return null
  }

  return (
    <div className="bg-heritage-container flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-6 text-center">
        <Clock
          className="text-heritage-container-foreground mx-auto h-12 w-12"
          aria-hidden="true"
        />

        <div className="space-y-2">
          <h1 className="text-heritage-container-foreground font-serif text-2xl">
            {t('pending_screen_heading')}
          </h1>
          <p className="text-heritage-container-foreground text-sm">
            {t('pending_screen_body_no_clan')}
          </p>
        </div>

        <ol className="text-heritage-container-foreground space-y-2 text-left text-sm">
          <li className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('pending_screen_step_account')}
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('pending_screen_step_request')}
          </li>
          <li className="flex items-center gap-2">
            <Circle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('pending_screen_step_waiting')}
          </li>
        </ol>

        <div role="status" aria-live="polite" className="min-h-5 text-sm">
          {recheckStatus === 'still-pending' && (
            <p className="text-heritage-container-foreground">
              {t('pending_screen_recheck_still_pending')}
            </p>
          )}
          {recheckStatus === 'error' && (
            <p className="text-destructive">{t('pending_screen_recheck_error')}</p>
          )}
        </div>

        <div className="flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={() => void handleRecheck()}
            disabled={recheckStatus === 'checking'}
            className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring w-full max-w-xs rounded-full px-4 py-2.5 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:cursor-not-allowed disabled:opacity-50"
          >
            {recheckStatus === 'checking'
              ? t('pending_screen_recheck_checking')
              : t('pending_screen_recheck_button')}
          </button>

          <Link
            href={`/${locale}/register?mode=oauth`}
            className="text-heritage-container-foreground text-sm underline-offset-2 hover:underline"
          >
            {t('pending_screen_join_another')}
          </Link>

          <button
            type="button"
            onClick={() => void signOut()}
            className="text-heritage-container-foreground/80 hover:text-heritage-container-foreground text-sm"
          >
            {t('logout')}
          </button>
        </div>
      </div>
    </div>
  )
}
