'use client'

import { useCallback, useEffect, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useAuth } from '@/lib/hooks/useAuth'

/**
 * `selectClan` (`useAuth.ts`) calls the legacy axios client (`src/lib/api/axios.ts`,
 * frozen). S-027 audited whether this seed deletes it and found it cannot: `axios.ts` is
 * the shared transport for every remaining legacy slice (admin, documents, events, persons,
 * relationships, tree — `grep -rln "lib/api/axios\|from 'axios'" src`, 2026-08-22), not an
 * auth-only file, and deleting it would break all of them. It leaves only when the last
 * slice PR replaces it — see `web/CLAUDE.md`, "Migration notes". Its response interceptor
 * rejects with the raw `AxiosError` on anything but a 401 rather than
 * normalizing it into `ApiError` (`shared/http/errors.ts`). The backend's envelope
 * (`docs/contracts/error-codes.md`: `{"error": {"code", "message", "detail"}}`) still sits at
 * `error.response.data.error.code` on that rejection — this reads it there without importing
 * anything from the axios tree, so the routing decision below is on the real `code`, per
 * `web/CLAUDE.md`'s "branch on the error code, never on message" rule, and not on a guess.
 */
function backendErrorCode(cause: unknown): string | null {
  if (typeof cause !== 'object' || cause === null || !('response' in cause)) return null
  const response = (cause as { response?: unknown }).response
  if (typeof response !== 'object' || response === null || !('data' in response)) return null
  const data = (response as { data?: unknown }).data
  if (typeof data !== 'object' || data === null || !('error' in data)) return null
  const error = (data as { error?: unknown }).error
  if (typeof error !== 'object' || error === null || !('code' in error)) return null
  const code = (error as { code?: unknown }).code
  return typeof code === 'string' ? code : null
}

export default function SelectClanPage() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const {
    clanMemberships,
    currentClanId,
    isLoading,
    isAuthenticated,
    isPendingApproval,
    needsOnboarding,
    selectClan,
  } = useAuth()
  const [selectedClanId, setSelectedClanId] = useState(currentClanId ?? '')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, startTransition] = useTransition()

  /** Shared by the manual submit handler and the single-clan auto-select effect below. */
  const routeOnSelectClanFailure = useCallback(
    (cause: unknown, clanId: string) => {
      const code = backendErrorCode(cause)
      if (code === 'clan_suspended') {
        const membership = clanMemberships.find((entry) => entry.clan_id === clanId)
        const params = new URLSearchParams({ clanId })
        if (membership?.clan_name) params.set('clanName', membership.clan_name)
        router.push(`/${locale}/clan-suspended?${params.toString()}`)
        return true
      }
      return false
    },
    [clanMemberships, locale, router],
  )

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push(`/${locale}/login`)
      return
    }

    if (!isLoading && isPendingApproval) {
      router.push(`/${locale}/pending-approval`)
      return
    }

    if (!isLoading && needsOnboarding) {
      router.push(`/${locale}/register?mode=oauth`)
      return
    }

    if (!isLoading && clanMemberships.length === 1 && clanMemberships[0]?.clan_id) {
      const onlyClanId = clanMemberships[0].clan_id
      void selectClan(onlyClanId)
        .then(() => {
          router.push(`/${locale}/dashboard`)
        })
        .catch((cause: unknown) => {
          // This branch used to have no `.catch()` at all — a suspended single-clan
          // user's auto-select rejected silently (an unhandled promise rejection),
          // never reaching a screen. Routed the same way the manual path below is.
          if (!routeOnSelectClanFailure(cause, onlyClanId)) {
            setError(cause instanceof Error ? cause.message : t('pending_subtitle'))
          }
        })
    }
  }, [
    clanMemberships,
    isAuthenticated,
    isLoading,
    isPendingApproval,
    needsOnboarding,
    locale,
    router,
    routeOnSelectClanFailure,
    selectClan,
    t,
  ])

  return (
    <div className="bg-background min-h-screen px-4 py-12">
      <div className="mx-auto max-w-xl rounded-3xl border border-gray-100 bg-white p-8 shadow-xs">
        <div className="space-y-2">
          <h1 className="font-serif text-3xl text-gray-900">Choose your clan</h1>
          <p className="text-sm text-gray-500">
            Select the clan context you want to work in. This controls permissions and all
            clan-scoped data.
          </p>
        </div>

        <div className="mt-6 space-y-3">
          {clanMemberships.map((membership) => (
            <label
              key={membership.clan_id}
              className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-4 transition-colors ${
                selectedClanId === membership.clan_id
                  ? 'border-primary bg-primary-container'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="clan"
                value={membership.clan_id}
                checked={selectedClanId === membership.clan_id}
                onChange={() => setSelectedClanId(membership.clan_id)}
                className="mt-1"
              />
              <span className="min-w-0">
                <span className="block text-base font-medium text-gray-900">
                  {membership.clan_name}
                </span>
                <span className="block text-xs tracking-wide text-gray-400 uppercase">
                  {membership.clan_slug}
                </span>
                <span className="mt-1 inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                  {membership.role}
                </span>
              </span>
            </label>
          ))}
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
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
            {isSubmitting ? t('loading') : 'Continue'}
          </button>
        </div>
      </div>
    </div>
  )
}
