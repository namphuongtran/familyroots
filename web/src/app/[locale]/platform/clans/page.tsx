'use client'

import { useTranslations } from 'next-intl'
import { usePlatformClans } from '@/lib/hooks/useAdmin'
import { formatDate } from '@/lib/utils/date'

export default function PlatformClansPage() {
  const t = useTranslations('platform')
  const { data, isLoading } = usePlatformClans()

  return (
    <div className="space-y-4">
      <h1 className="font-serif text-2xl text-gray-800">{t('clans_title')}</h1>

      {isLoading ? (
        <p className="text-sm text-gray-400">Đang tải…</p>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-xs divide-y divide-gray-50">
          {(data ?? []).map(clan => (
            <div key={clan.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-medium text-gray-700">{clan.name}</p>
                <p className="text-xs text-gray-400">{clan.created_at ? formatDate(clan.created_at) : '-'}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-500">{clan.slug}</span>
                <span
                  className={`text-[10px] rounded px-1.5 py-0.5 ${clan.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'}`}
                >
                  {clan.is_active ? 'Hoạt động' : 'Tạm ngưng'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
