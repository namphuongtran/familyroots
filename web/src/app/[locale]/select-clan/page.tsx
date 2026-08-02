'use client'

import { useEffect, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useAuth } from '@/lib/hooks/useAuth'

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
      void selectClan(clanMemberships[0].clan_id).then(() => {
        router.push(`/${locale}/dashboard`)
      })
    }
  }, [clanMemberships, isAuthenticated, isLoading, isPendingApproval, needsOnboarding, locale, router, selectClan])

  return (
    <div className="min-h-screen bg-cream px-4 py-12">
      <div className="mx-auto max-w-xl rounded-3xl border border-gray-100 bg-white p-8 shadow-xs">
        <div className="space-y-2">
          <h1 className="font-serif text-3xl text-gray-900">Choose your clan</h1>
          <p className="text-sm text-gray-500">
            Select the clan context you want to work in. This controls permissions and all clan-scoped data.
          </p>
        </div>

        <div className="mt-6 space-y-3">
          {clanMemberships.map((membership) => (
            <label
              key={membership.clan_id}
              className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-4 transition-colors ${
                selectedClanId === membership.clan_id
                  ? 'border-primary-500 bg-primary-50'
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
                <span className="block text-base font-medium text-gray-900">{membership.clan_name}</span>
                <span className="block text-xs uppercase tracking-wide text-gray-400">{membership.clan_slug}</span>
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
                  setError(cause instanceof Error ? cause.message : t('pending_subtitle'))
                }
              })
            }}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {isSubmitting ? t('loading') : 'Continue'}
          </button>
        </div>
      </div>
    </div>
  )
}
