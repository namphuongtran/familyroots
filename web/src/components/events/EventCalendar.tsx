'use client'

import { useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isToday, isSameDay, addMonths, subMonths } from 'date-fns'
import { vi } from 'date-fns/locale'
import { EventCard } from './EventCard'
import { useEvents } from '@/lib/hooks/useEvents'
import { cn } from '@/lib/utils/cn'

export function EventCalendar() {
  const t = useTranslations('events')
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [selectedDate, setSelectedDate] = useState<Date | null>(null)
  const { data } = useEvents()

  const events = data?.pages.flatMap(p => p.data) ?? []

  const daysInMonth = useMemo(() => {
    return eachDayOfInterval({
      start: startOfMonth(currentMonth),
      end: endOfMonth(currentMonth),
    })
  }, [currentMonth])

  const eventsOnDay = (day: Date) =>
    events.filter(e => isSameDay(new Date(e.event_date), day))

  const selectedDayEvents = selectedDate ? eventsOnDay(selectedDate) : []

  return (
    <div className="space-y-4">
      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <button onClick={() => setCurrentMonth(m => subMonths(m, 1))} className="p-1 rounded hover:bg-gray-100">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-semibold text-gray-700 capitalize">
          {format(currentMonth, 'MMMM yyyy', { locale: vi })}
        </span>
        <button onClick={() => setCurrentMonth(m => addMonths(m, 1))} className="p-1 rounded hover:bg-gray-100">
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="grid grid-cols-7 text-center text-[10px] text-gray-400 font-medium">
        {['CN', 'Th2', 'Th3', 'Th4', 'Th5', 'Th6', 'Th7'].map(d => (
          <div key={d}>{d}</div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-0.5">
        {/* Leading empty cells for first day offset */}
        {Array.from({ length: daysInMonth[0].getDay() }).map((_, i) => (
          <div key={`empty-${i}`} className="h-8" />
        ))}
        {daysInMonth.map(day => {
          const dayEvents = eventsOnDay(day)
          const isSelected = selectedDate && isSameDay(day, selectedDate)
          return (
            <button
              key={day.toISOString()}
              onClick={() => setSelectedDate(isSameDay(day, selectedDate ?? new Date(0)) ? null : day)}
              className={cn(
                'h-8 flex flex-col items-center justify-center rounded text-xs relative',
                !isSameMonth(day, currentMonth) && 'text-gray-300',
                isToday(day) && 'text-primary font-bold',
                isSelected && 'bg-primary-container ring-1 ring-ring',
                !isSelected && 'hover:bg-gray-100',
              )}
            >
              {day.getDate()}
              {dayEvents.length > 0 && (
                <span className="absolute bottom-0.5 h-1 w-1 rounded-full bg-gold-500" />
              )}
            </button>
          )
        })}
      </div>

      {/* Selected day events */}
      {selectedDate && (
        <div className="space-y-2 pt-2 border-t border-gray-100">
          <p className="text-xs font-medium text-gray-500">
            {format(selectedDate, 'd MMMM yyyy', { locale: vi })}
          </p>
          {selectedDayEvents.length === 0 ? (
            <p className="text-xs text-gray-400 italic">{t('no_events_on_day')}</p>
          ) : (
            selectedDayEvents.map(e => <EventCard key={e.id} event={e} />)
          )}
        </div>
      )}
    </div>
  )
}
