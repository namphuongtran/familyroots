'use client'

import { useTranslations } from 'next-intl'
import { Calendar, MapPin, Users } from 'lucide-react'
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
        'p-4 rounded-xl border',
        EVENT_COLORS[event.event_type] ?? EVENT_COLORS.other,
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-800 truncate">{event.title}</h3>
          {event.description && (
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{event.description}</p>
          )}
        </div>
        <span className="text-[10px] bg-white/70 border border-current rounded px-1.5 py-0.5 text-gray-500 shrink-0">
          {t(`type.${event.event_type}`)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {formatDate(event.event_date)}
          {event.end_date && ` – ${formatDate(event.end_date)}`}
        </span>
        {event.location && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {event.location}
          </span>
        )}
      </div>
    </div>
  )
}
