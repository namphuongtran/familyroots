'use client'

import { useLocale, useTranslations } from 'next-intl'
import { Calendar } from 'lucide-react'
import type { UpcomingEvent } from '@/domain/event/event'
import { formatHistoricalDate, isKnownDate } from '@/features/persons'
import { cn } from '@/lib/utils/cn'
import { formatSolarDate } from './format-event-date'

const EVENT_TYPES = [
  'death_anniversary',
  'birthday',
  'wedding_anniversary',
  'clan_ceremony',
  'custom',
] as const
type KnownEventType = (typeof EVENT_TYPES)[number]

function knownType(value: string): KnownEventType {
  return (EVENT_TYPES as readonly string[]).includes(value) ? (value as KnownEventType) : 'custom'
}

// ADR-055: every card names its kind in the type chip, so colour is decoration, not the
// identifying channel. Only a giỗ keeps a tone of its own (spec § 7.8: `heritage-container`).
const EVENT_COLORS: Record<KnownEventType, string> = {
  death_anniversary: 'bg-heritage-container border-heritage',
  birthday: 'bg-muted border-border',
  wedding_anniversary: 'bg-muted border-border',
  clan_ceremony: 'bg-accent border-accent-foreground/30',
  custom: 'bg-muted border-border',
}

interface EventCardProps {
  event: UpcomingEvent
}

/**
 * One upcoming event, spec § 7.8. The two dates are labelled apart (§ 9-J7): the recorded
 * `HistoricalDate`, through the contract's render rule, and the backend's solar
 * `nextOccurrence`. A lunar event says it is lunar and names its next date as solar, because that
 * date is ADR-018's conversion of the lunar anniversary, not the recorded day and month.
 */
export function EventCard({ event }: EventCardProps) {
  const t = useTranslations('events')
  const locale = useLocale()
  const type = knownType(event.eventType)
  const next = formatSolarDate(event.nextOccurrence, locale)

  return (
    <article className={cn('rounded-xl border p-4', EVENT_COLORS[type])}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-foreground text-sm font-semibold">{event.title}</h3>
          {event.personName && (
            <p className="text-muted-foreground mt-0.5 text-xs">{event.personName}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {event.isLunarCalendar && (
            <span className="text-muted-foreground bg-card/70 rounded border border-current px-1.5 py-0.5 text-[10px]">
              {t('lunar_label')}
            </span>
          )}
          <span className="text-muted-foreground bg-card/70 rounded border border-current px-1.5 py-0.5 text-[10px]">
            {t(`type.${type}`)}
          </span>
        </div>
      </div>

      <div className="text-muted-foreground mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="flex items-center gap-1">
          <Calendar aria-hidden="true" className="h-3 w-3" />
          {event.isLunarCalendar
            ? t(type === 'death_anniversary' ? 'next_occurrence_gio' : 'next_occurrence_lunar', {
                date: next,
              })
            : next}
        </span>
        <span className="bg-card/70 text-foreground rounded-full px-2 py-0.5 font-medium">
          {t('days_until', { count: event.daysUntil })}
        </span>
      </div>

      {isKnownDate(event.eventDate) && (
        <p className="text-muted-foreground mt-1 text-xs">
          {t('recorded_date', { date: formatHistoricalDate(event.eventDate, locale, '') })}
        </p>
      )}
      {event.eventDate?.lunar && (
        <p className="text-muted-foreground mt-1 text-xs">
          {t('recorded_lunar', { lunar: event.eventDate.lunar })}
        </p>
      )}
    </article>
  )
}
