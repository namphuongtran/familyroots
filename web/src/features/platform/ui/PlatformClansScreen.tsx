'use client'

import { useTranslations } from 'next-intl'
import { formatDate } from '@/lib/utils/date'
import { useClientRequestContext } from '@/shared/http/context.client'
import { usePlatformClans } from '../hooks/use-platform-queries'

/** Every clan on the platform, for the super-admin. */
export function PlatformClansScreen() {
  const t = useTranslations('platform')
  const tCommon = useTranslations('common')
  const request = useClientRequestContext({ clanScoped: false })
  const clans = usePlatformClans({
    context: request.context,
    refreshAuth: request.refreshAuth,
    enabled: request.ready,
  })

  return (
    <div className="space-y-4">
      <h1 className="text-foreground font-serif text-2xl">{t('clans_title')}</h1>

      {!request.ready || clans.isPending ? (
        <p className="text-muted-foreground text-sm">{tCommon('loading')}</p>
      ) : (
        <div className="divide-border border-border bg-card divide-y rounded-2xl border shadow-xs">
          {(clans.data ?? []).map((clan) => (
            <div key={clan.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-foreground text-sm font-medium">{clan.name}</p>
                <p className="text-muted-foreground text-xs">
                  {clan.createdAt ? formatDate(clan.createdAt) : '-'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground text-xs">{clan.slug}</span>
                {/*
                  ADR-055: `is_active` is a real two-state status, unlike the
                  stat tiles above, and its text already carries the state
                  too (`platform.active` / `platform.inactive`), so this is decoration on
                  top of information rather than the only channel. `bg-green-
                  100 text-green-700` had no dark value; `success` does.
                */}
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] ${clan.isActive ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'}`}
                >
                  {clan.isActive ? t('active') : t('inactive')}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
