'use client'

/**
 * Spec §7.2a (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:904-930`),
 * the screen for a signed-in user with no *approved* clan membership yet. Triggered by
 * `useAuth()`'s `isPendingApproval` (`src/lib/hooks/useAuth.ts` → `hydrateAuthContext`,
 * `src/application/auth/use-cases/auth-context.ts`), which is true when the profile carries
 * `has_pending_membership: true` and zero approved memberships — the same fact the backend's
 * `no_approved_clan_membership` 403 guards on clan-scoped routes
 * (`docs/contracts/frontend-integration-guide.md` §1.2/§5). This screen only ever renders for
 * the genuinely-pending case; the "no membership at all" onboarding variant the spec describes
 * as living in the *same* screen is, in this codebase, already a separate route —
 * `useAuth().needsOnboarding` sends the user to `/register?mode=oauth`, which already has the
 * join/create segmented control (spec §7.1b). Duplicating that form here would be two
 * implementations of one flow, so this screen redirects to it instead of rebuilding it.
 *
 * **The `{clanName}` the spec's copy assumes is not reliably available, and this is a real
 * contract gap, not a bug in this screen.** `GET /auth/me` and `GET /me/clans` are both
 * documented as joining on *approved* memberships only (`rest-auth-api.md` §1.1,
 * `frontend-integration-guide.md` §1.2), so neither ever returns the name of a clan the user
 * has only a *pending* membership in. `POST /auth/login`'s `user.clan_name` does carry it
 * ("reflects one membership row, including a pending one" — `frontend-integration-guide.md`
 * §1.1), but the live sign-in path never calls that endpoint (see the comment in
 * `VerifyEmailScreen.tsx` for the same finding), and even the legacy code that does read a
 * profile discards it by joining on approved memberships only
 * (`src/application/auth/use-cases/auth-context.ts`'s `hydrateAuthContext`). There is today no
 * source in this codebase that resolves a pending clan's name once the join request has been
 * sent. `pending_screen_body_no_clan` is the fallback for that case, and it renders whenever
 * `user?.clan_name` is empty rather than showing a stale or invented name.
 *
 * **This screen does not promise a notification on approval, unlike the spec's literal copy**
 * ("Chúng tôi sẽ gửi thông báo ngay khi bạn được duyệt", design spec line 915-916). S-026's own
 * seed text overrides that: "the pending screen ... does not promise a notification" and lists
 * "Any notification, because none exists for any queue event" as out of scope. No notification
 * pipeline fires on membership approval today, so promising one would be a false statement to
 * the user. Read the seed at `docs/SEEDS.md`, "## S-026", over the older spec prose where the
 * two disagree.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { CheckCircle2, Circle, Clock } from 'lucide-react'
import { useAuth } from '@/lib/hooks/useAuth'
import { apiFetch } from '@/shared/http/api-client'
import { getClientRequestContext } from '@/shared/http/context.client'
import { unwrapData } from '@/shared/http/envelope'

interface MeSnapshot {
  isApproved: boolean
}

/** `GET /auth/me` (`rest-auth-api.md`): the profile object directly under `data`. */
function parseMeSnapshot(raw: unknown): MeSnapshot {
  if (typeof raw !== 'object' || raw === null) {
    throw new Error('GET /auth/me did not return an object')
  }
  return { isApproved: (raw as { is_approved?: unknown }).is_approved === true }
}

type RecheckStatus = 'idle' | 'checking' | 'still-pending' | 'error'

export function PendingApprovalScreen() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const {
    user,
    isLoading,
    isAuthenticated,
    isPendingApproval,
    needsOnboarding,
    signOut,
    syncAuthContext,
  } = useAuth()
  const [recheckStatus, setRecheckStatus] = useState<RecheckStatus>('idle')

  useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace(`/${locale}/login`)
      return
    }
    if (needsOnboarding) {
      router.replace(`/${locale}/register?mode=oauth`)
      return
    }
    if (!isPendingApproval) {
      router.replace(`/${locale}/dashboard`)
    }
  }, [isAuthenticated, isLoading, isPendingApproval, locale, needsOnboarding, router])

  async function handleRecheck() {
    setRecheckStatus('checking')
    try {
      const context = await getClientRequestContext()
      const body = await apiFetch('/auth/me', { context })
      const snapshot = unwrapData(body, parseMeSnapshot)
      if (snapshot.isApproved) {
        // Refresh the legacy store/cookie before navigating, so the dashboard
        // does not render against a stale `isPendingApproval` read from the store.
        await syncAuthContext()
        router.push(`/${locale}/dashboard`)
        return
      }
      setRecheckStatus('still-pending')
    } catch {
      setRecheckStatus('error')
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <p className="text-sm text-muted-foreground">{t('loading')}</p>
      </div>
    )
  }

  if (!isPendingApproval) {
    // Mid-redirect (the effect above already fired). Render nothing rather
    // than a flash of this screen's content.
    return null
  }

  const clanName = user?.clan_name

  return (
    <div className="flex min-h-screen items-center justify-center bg-heritage-container px-4 py-12">
      <div className="w-full max-w-md space-y-6 text-center">
        <Clock className="mx-auto h-12 w-12 text-heritage-container-foreground" aria-hidden="true" />

        <div className="space-y-2">
          <h1 className="font-serif text-2xl text-heritage-container-foreground">
            {t('pending_screen_heading')}
          </h1>
          <p className="text-sm text-heritage-container-foreground">
            {clanName
              ? t('pending_screen_body_with_clan', { clanName })
              : t('pending_screen_body_no_clan')}
          </p>
        </div>

        <ol className="space-y-2 text-left text-sm text-heritage-container-foreground">
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
            className="w-full max-w-xs rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {recheckStatus === 'checking'
              ? t('pending_screen_recheck_checking')
              : t('pending_screen_recheck_button')}
          </button>

          <Link
            href={`/${locale}/register?mode=oauth`}
            className="text-sm text-heritage-container-foreground underline-offset-2 hover:underline"
          >
            {t('pending_screen_join_another')}
          </Link>

          <button
            type="button"
            onClick={() => void signOut()}
            className="text-sm text-heritage-container-foreground/80 hover:text-heritage-container-foreground"
          >
            {t('logout')}
          </button>
        </div>
      </div>
    </div>
  )
}
