'use client'

import { useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import {
  format,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  isSameMonth,
  isToday,
  isSameDay,
  addMonths,
  subMonths,
} from 'date-fns'
import { vi } from 'date-fns/locale'
import { EventCard } from './EventCard'
import { useEvents } from '@/lib/hooks/useEvents'
import { cn } from '@/lib/utils/cn'

export function EventCalendar() {
  const t = useTranslations('events')
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [selectedDate, setSelectedDate] = useState<Date | null>(null)
  const { data } = useEvents()

  const events = data?.pages.flatMap((p) => p.data) ?? []

  const daysInMonth = useMemo(() => {
    return eachDayOfInterval({
      start: startOfMonth(currentMonth),
      end: endOfMonth(currentMonth),
    })
  }, [currentMonth])

  const eventsOnDay = (day: Date) => events.filter((e) => isSameDay(new Date(e.event_date), day))

  const selectedDayEvents = selectedDate ? eventsOnDay(selectedDate) : []

  return (
    <div className="space-y-4">
      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
          className="hover:bg-muted rounded p-1"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-foreground text-sm font-semibold capitalize">
          {format(currentMonth, 'MMMM yyyy', { locale: vi })}
        </span>
        <button
          onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
          className="hover:bg-muted rounded p-1"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="text-muted-foreground grid grid-cols-7 text-center text-[10px] font-medium">
        {['CN', 'Th2', 'Th3', 'Th4', 'Th5', 'Th6', 'Th7'].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-0.5">
        {/* Leading empty cells for first day offset */}
        {Array.from({ length: daysInMonth[0].getDay() }).map((_, i) => (
          <div key={`empty-${i}`} className="h-8" />
        ))}
        {daysInMonth.map((day) => {
          const dayEvents = eventsOnDay(day)
          const isSelected = selectedDate && isSameDay(day, selectedDate)
          return (
            <button
              key={day.toISOString()}
              onClick={() =>
                setSelectedDate(isSameDay(day, selectedDate ?? new Date(0)) ? null : day)
              }
              aria-label={
                dayEvents.length > 0
                  ? `${format(day, 'd MMMM yyyy', { locale: vi })}, ${t('day_events_count', { count: dayEvents.length })}`
                  : undefined
              }
              className={cn(
                'relative flex h-8 flex-col items-center justify-center rounded text-xs',
                !isSameMonth(day, currentMonth) && 'text-muted-foreground',
                isToday(day) && 'text-primary font-bold',
                isSelected && 'bg-primary-container ring-ring ring-1',
                !isSelected && 'hover:bg-muted',
              )}
            >
              {day.getDate()}
              {dayEvents.length > 0 && (
                // T-06 (spec § 5): colour is never the sole channel. A gold
                // dot alone (`bg-gold-500` on `cream`, 2.03:1, S-036) is
                // invisible in greyscale and to a screen reader. This badge
                // carries the event count as text — `primary`/`primary-foreground`
                // is already gated at ≥4.5:1 on every ground in
                // `contrast.test.ts` — and the count reaches a screen reader
                // through the button's own `aria-label` above, so the badge
                // itself is `aria-hidden`.
                <span
                  aria-hidden="true"
                  className="bg-primary text-primary-foreground absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-0.5 text-[10px] leading-none font-semibold"
                >
                  {dayEvents.length > 9 ? '9+' : dayEvents.length}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Selected day events */}
      {selectedDate && (
        <div className="border-border space-y-2 border-t pt-2">
          <p className="text-muted-foreground text-xs font-medium">
            {format(selectedDate, 'd MMMM yyyy', { locale: vi })}
          </p>
          {selectedDayEvents.length === 0 ? (
            <p className="text-muted-foreground text-xs italic">{t('no_events_on_day')}</p>
          ) : (
            selectedDayEvents.map((e) => <EventCard key={e.id} event={e} />)
          )}
        </div>
      )}
    </div>
  )
}
