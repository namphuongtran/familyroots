'use client'

import { useCallback, useEffect, useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import type { Membership } from '@/domain/session/session'
import { cn } from '@/lib/utils/cn'
import { ApiError } from '@/shared/http/errors'
import { useAuthActions } from '../hooks/use-auth-actions'
import { useSession } from '../hooks/use-session'
import { landingPath } from '../model/landing'

/** `docs/contracts/error-codes.md`, "Clan context & permissions". */
const CLAN_SUSPENDED_CODE = 'clan_suspended'

/** One empty list, so an effect that depends on the memberships does not re-run every render. */
const NO_MEMBERSHIPS: readonly Membership[] = []

/**
 * The clan picker. `app/[locale]/select-clan/page.tsx` only routes here.
 *
 * Selecting goes through `apiFetch` now, so a refusal is an `ApiError` and its `code` is read
 * off the error itself. Before #183 it went through the legacy axios client, which left the
 * envelope at `error.response.data.error`, and this screen carried a reader for that shape.
 *
 * A user with one approved membership never chooses: the screen selects it for them, once.
 * Anyone whose access state is not "choose a clan" or "ready" is sent where it says.
 */
export function SelectClanScreen() {
  const t = useTranslations('auth')
  // Two reused keys, each already saying the same thing in all four locales (#197). The heading
  // is the words of the invitation link that opens this screen, and the button is the person
  // form's `Continue`.
  const tInvitation = useTranslations('invitation')
  const tMemberForm = useTranslations('member_form')
  const locale = useLocale()
  const router = useRouter()
  const { session, access, activeClan } = useSession()
  const { selectClan } = useAuthActions()
  const memberships = session?.memberships ?? NO_MEMBERSHIPS
  const activeClanId = activeClan?.clanId ?? ''
  const [pickedClanId, setPickedClanId] = useState<string | null>(null)
  const selectedClanId = pickedClanId ?? activeClanId
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, startTransition] = useTransition()
  const autoSelected = useRef(false)

  /** Shared by the manual submit handler and the single-clan auto-select effect below. */
  const routeOnSelectClanFailure = useCallback(
    (cause: unknown, clanId: string) => {
      if (cause instanceof ApiError && cause.code === CLAN_SUSPENDED_CODE) {
        const membership = memberships.find((entry) => entry.clanId === clanId)
        const params = new URLSearchParams({ clanId })
        if (membership?.clanName) params.set('clanName', membership.clanName)
        router.push(`/${locale}/clan-suspended?${params.toString()}`)
        return true
      }
      return false
    },
    [memberships, locale, router],
  )

  useEffect(() => {
    if (access === null) return

    if (access.kind !== 'ready' && access.kind !== 'needs-clan-selection') {
      router.push(landingPath(access, locale))
      return
    }

    // `autoSelected` keeps this to one request: the cookie write re-renders this screen with
    // a new access state, and nothing else here should select again on that render.
    if (memberships.length === 1 && !autoSelected.current) {
      autoSelected.current = true
      const onlyClanId = memberships[0].clanId
      void selectClan(onlyClanId)
        .then(() => {
          router.push(`/${locale}/dashboard`)
        })
        .catch((cause: unknown) => {
          // A suspended single-clan user's auto-select used to reject silently, an unhandled
          // promise rejection that never reached a screen. Routed the same way as the manual path.
          if (!routeOnSelectClanFailure(cause, onlyClanId)) {
            setError(cause instanceof Error ? cause.message : t('pending_subtitle'))
          }
        })
    }
  }, [access, locale, memberships, router, routeOnSelectClanFailure, selectClan, t])

  return (
    <div className="bg-background min-h-screen px-4 py-12">
      <div className="border-border bg-card mx-auto max-w-xl rounded-3xl border p-8 shadow-xs">
        <div className="space-y-2">
          <h1 className="text-foreground font-serif text-3xl">{tInvitation('continue_button')}</h1>
          <p className="text-muted-foreground text-sm">{t('select_clan_subtitle')}</p>
        </div>

        <div className="mt-6 space-y-3">
          {memberships.map((membership) => (
            <label
              key={membership.clanId}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-4 transition-colors',
                selectedClanId === membership.clanId
                  ? 'border-primary bg-primary-container'
                  : 'border-border hover:border-input',
              )}
            >
              <input
                type="radio"
                name="clan"
                value={membership.clanId}
                checked={selectedClanId === membership.clanId}
                onChange={() => setPickedClanId(membership.clanId)}
                className="mt-1"
              />
              <span className="min-w-0">
                <span className="text-foreground block text-base font-medium">
                  {membership.clanName}
                </span>
                <span className="text-muted-foreground block text-xs tracking-wide uppercase">
                  {membership.clanSlug}
                </span>
                <span className="bg-muted text-muted-foreground mt-1 inline-flex rounded-full px-2 py-0.5 text-xs">
                  {membership.role}
                </span>
              </span>
            </label>
          ))}
        </div>

        {error && (
          <div className="border-destructive/30 bg-destructive/10 text-destructive mt-4 rounded-lg border px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="mt-6 flex items-center gap-3">
          <button
            type="button"
            disabled={!selectedClanId || isSubmitting}
            onClick={() => {
              setError(null)
              startTransition(async () => {
                try {
                  await selectClan(selectedClanId)
                  router.push(`/${locale}/dashboard`)
                } catch (cause) {
                  if (!routeOnSelectClanFailure(cause, selectedClanId)) {
                    setError(cause instanceof Error ? cause.message : t('pending_subtitle'))
                  }
                }
              })
            }}
            className="bg-primary text-primary-foreground hover:bg-primary-hover rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {isSubmitting ? t('loading') : tMemberForm('continue_label')}
          </button>
        </div>
      </div>
    </div>
  )
}
