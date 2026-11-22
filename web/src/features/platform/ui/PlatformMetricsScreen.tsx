'use client'

import { useTranslations } from 'next-intl'
import { useClientRequestContext } from '@/shared/http/context.client'
import { usePlatformMetrics } from '../hooks/use-platform-queries'

/** The platform-wide totals, for the super-admin. */
export function PlatformMetricsScreen() {
  const t = useTranslations('platform')
  const request = useClientRequestContext({ clanScoped: false })
  const metrics = usePlatformMetrics({
    context: request.context,
    refreshAuth: request.refreshAuth,
    enabled: request.ready,
  })
  const data = metrics.data

  // ADR-055: these five tiles used to rotate through five untokened hues
  // (blue, purple, rose, green, plus the one already-tokened `accent`
  // entry), one per metric, with no metric's severity or state behind the
  // choice — a metric count going up or down does not change which colour it
  // gets. That is decoration, not information, so all five now share the one
  // existing `accent` pair rather than gaining four more one-off families.
  const tiles: Array<{ label: string; value: number | undefined }> = [
    { label: t('total_clans'), value: data?.totalClans },
    { label: t('active_clans'), value: data?.activeClans },
    { label: t('suspended_clans'), value: data?.suspendedClans },
    { label: t('total_members'), value: data?.totalMembers },
    { label: t('total_users'), value: data?.totalUsers },
  ]

  return (
    <div className="space-y-4">
      <h1 className="text-foreground font-serif text-2xl">{t('metrics_title')}</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {tiles.map(({ label, value }) => (
          <div
            key={label}
            className="bg-accent text-accent-foreground flex flex-col gap-1 rounded-2xl p-4"
          >
            <p className="text-2xl font-bold">{value ?? '—'}</p>
            <p className="text-xs opacity-70">{label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
