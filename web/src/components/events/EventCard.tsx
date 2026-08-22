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
  death_anniversary: 'bg-red-50 border-red-200',
  birthday: 'bg-blue-50 border-blue-200',
  wedding_anniversary: 'bg-pink-50 border-pink-200',
  clan_ceremony: 'bg-amber-50 border-amber-200',
  custom: 'bg-gray-50 border-gray-200',
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
          <h3 className="truncate text-sm font-semibold text-gray-800">{event.title}</h3>
          {event.description && (
            <p className="mt-0.5 line-clamp-2 text-xs text-gray-500">{event.description}</p>
          )}
        </div>
        <span className="shrink-0 rounded border border-current bg-white/70 px-1.5 py-0.5 text-[10px] text-gray-500">
          {t(`type.${event.event_type}`)}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {formatDate(event.event_date)}
        </span>
      </div>
    </div>
  )
}
