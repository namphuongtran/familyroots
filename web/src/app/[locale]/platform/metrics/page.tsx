'use client'

import { useTranslations } from 'next-intl'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api/axios'

interface PlatformMetrics {
  total_clans: number
  total_members: number
  total_users: number
  active_clans_30d: number
}

export default function PlatformMetricsPage() {
  const t = useTranslations('platform')

  const { data, isLoading } = useQuery({
    queryKey: ['platform', 'metrics'],
    queryFn: async () => {
      const res = await api.get<PlatformMetrics>('/platform/metrics')
      return res.data
    },
  })

  const metrics: Array<{ label: string; value: number | undefined; color: string }> = [
    { label: t('total_clans'), value: data?.total_clans, color: 'bg-blue-50 text-blue-700' },
    { label: t('total_members'), value: data?.total_members, color: 'bg-green-50 text-green-700' },
    { label: t('total_users'), value: data?.total_users, color: 'bg-amber-50 text-amber-700' },
    { label: t('active_clans_30d'), value: data?.active_clans_30d, color: 'bg-purple-50 text-purple-700' },
  ]

  return (
    <div className="space-y-4">
      <h1 className="font-serif text-2xl text-gray-800">{t('metrics_title')}</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
