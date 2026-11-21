'use client'

import { useMemo, useState } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  isToday,
  startOfMonth,
  subMonths,
} from 'date-fns'
import type { UpcomingEvent } from '@/domain/event/event'
import { cn } from '@/lib/utils/cn'
import { dayKey, formatLongDay, formatMonth, weekdayNames } from './format-event-date'

interface EventCalendarProps {
  events: UpcomingEvent[]
  /** `YYYY-MM-DD`, or null for no selection. */
  selectedDay: string | null
  onSelectDay: (day: string | null) => void
}

/**
 * The month grid, spec § 7.8: navigation only, the list is authoritative. An event sits on its
 * `nextOccurrence`, the solar date the backend computed, so a lunar giỗ lands on the day it is
 * observed this year rather than on its recorded solar day and month.
 *
 * T-06/T-13 (spec § 5): a day carrying events shows a count badge, never a colour dot alone, and a
 * screen reader hears the count through the day button's own accessible name.
 */
export function EventCalendar({ events, selectedDay, onSelectDay }: EventCalendarProps) {
  const t = useTranslations('events')
  const locale = useLocale()
  const [currentMonth, setCurrentMonth] = useState(() => startOfMonth(new Date()))

  const days = useMemo(
    () => eachDayOfInterval({ start: currentMonth, end: endOfMonth(currentMonth) }),
    [currentMonth],
  )
  const countByDay = useMemo(() => {
    const counts = new Map<string, number>()
    for (const event of events) {
      counts.set(event.nextOccurrence, (counts.get(event.nextOccurrence) ?? 0) + 1)
    }
    return counts
  }, [events])
  const weekdays = useMemo(() => weekdayNames(locale), [locale])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          type="button"
          aria-label={t('previous_month')}
          onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
          className="hover:bg-muted rounded p-1"
        >
          <ChevronLeft aria-hidden="true" className="h-4 w-4" />
        </button>
        <span className="text-foreground text-sm font-semibold capitalize">
          {formatMonth(currentMonth, locale)}
        </span>
        <button
          type="button"
          aria-label={t('next_month')}
          onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
          className="hover:bg-muted rounded p-1"
        >
          <ChevronRight aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>

      <div className="text-muted-foreground grid grid-cols-7 text-center text-[10px] font-medium">
        {weekdays.map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {Array.from({ length: currentMonth.getDay() }).map((_, i) => (
          <div key={`empty-${i}`} className="h-8" />
        ))}
        {days.map((day) => {
          const key = dayKey(day)
          const count = countByDay.get(key) ?? 0
          const isSelected = key === selectedDay
          return (
            <button
              type="button"
              key={key}
              aria-pressed={isSelected}
              onClick={() => onSelectDay(isSelected ? null : key)}
              aria-label={
                count > 0
                  ? `${formatLongDay(day, locale)}, ${t('day_events_count', { count })}`
                  : undefined
              }
              className={cn(
                'relative flex h-8 flex-col items-center justify-center rounded text-xs',
                isToday(day) && 'text-primary font-bold',
                isSelected && 'bg-primary-container ring-ring ring-1',
                !isSelected && 'hover:bg-muted',
              )}
            >
              {day.getDate()}
              {count > 0 && (
                // `primary`/`primary-foreground` is gated at ≥4.5:1 on every ground in
                // `contrast.test.ts`; the count reaches a screen reader through the
                // button's `aria-label`, so the badge itself is hidden.
                <span
                  aria-hidden="true"
                  className="bg-primary text-primary-foreground absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-0.5 text-[10px] leading-none font-semibold"
                >
                  {count > 9 ? '9+' : count}
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
