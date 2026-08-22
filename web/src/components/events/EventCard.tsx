'use client'

import { useTranslations } from 'next-intl'
import { Calendar } from 'lucide-react'
import { formatDate } from '@/lib/utils/date'
import { cn } from '@/lib/utils/cn'
import type { ClanEvent } from '@/lib/types'

interface EventCardProps {
  event: ClanEvent
  className?: string
}

const EVENT_COLORS: Record<string, string> = {
  death_anniversary: 'bg-heritage-container border-heritage',
  birthday: 'bg-blue-50 border-blue-200',
  wedding_anniversary: 'bg-pink-50 border-pink-200',
  clan_ceremony: 'bg-accent border-accent-foreground/30',
  custom: 'bg-muted border-border',
}

export function EventCard({ event, className }: EventCardProps) {
  const t = useTranslations('events')

  return (
    <div
      className={cn(
        'rounded-xl border p-4',
        EVENT_COLORS[event.event_type] ?? EVENT_COLORS.other,
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-foreground truncate text-sm font-semibold">{event.title}</h3>
          {event.description && (
            <p className="text-muted-foreground mt-0.5 line-clamp-2 text-xs">{event.description}</p>
          )}
        </div>
        <span className="text-muted-foreground shrink-0 rounded border border-current bg-white/70 px-1.5 py-0.5 text-[10px]">
          {t(`type.${event.event_type}`)}
        </span>
      </div>

      <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-3 text-xs">
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {formatDate(event.event_date)}
        </span>
      </div>
    </div>
  )
}
