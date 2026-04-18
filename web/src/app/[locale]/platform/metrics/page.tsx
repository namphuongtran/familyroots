'use client'

import { useTranslations } from 'next-intl'
import { usePlatformMetrics } from '@/lib/hooks/useAdmin'

export default function PlatformMetricsPage() {
  const t = useTranslations('platform')
  const { data, isLoading } = usePlatformMetrics()

  const metrics: Array<{ label: string; value: number | undefined; color: string }> = [
    { label: t('total_clans'), value: data?.total_clans, color: 'bg-blue-50 text-blue-700' },
    { label: t('active_clans'), value: data?.active_clans, color: 'bg-purple-50 text-purple-700' },
    { label: t('suspended_clans'), value: data?.suspended_clans, color: 'bg-rose-50 text-rose-700' },
    { label: t('total_members'), value: data?.total_members, color: 'bg-green-50 text-green-700' },
    { label: t('total_users'), value: data?.total_users, color: 'bg-amber-50 text-amber-700' },
  ]

  return (
    <div className="space-y-4">
      <h1 className="font-serif text-2xl text-gray-800">{t('metrics_title')}</h1>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {metrics.map(({ label, value, color }) => (
          <div key={label} className={`rounded-2xl p-4 ${color} flex flex-col gap-1`}>
            <p className="text-2xl font-bold">{isLoading ? '—' : value}</p>
            <p className="text-xs opacity-70">{label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
