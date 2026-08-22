'use client'

import { useTranslations } from 'next-intl'
import { usePlatformClans } from '@/lib/hooks/useAdmin'
import { formatDate } from '@/lib/utils/date'

export default function PlatformClansPage() {
  const t = useTranslations('platform')
  const { data, isLoading } = usePlatformClans()

  return (
    <div className="space-y-4">
      <h1 className="text-foreground font-serif text-2xl">{t('clans_title')}</h1>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Đang tải…</p>
      ) : (
        <div className="divide-border border-border bg-card divide-y rounded-2xl border shadow-xs">
          {(data ?? []).map((clan) => (
            <div key={clan.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-foreground text-sm font-medium">{clan.name}</p>
                <p className="text-muted-foreground text-xs">
                  {clan.created_at ? formatDate(clan.created_at) : '-'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground text-xs">{clan.slug}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] ${clan.is_active ? 'bg-green-100 text-green-700' : 'bg-muted text-muted-foreground'}`}
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
