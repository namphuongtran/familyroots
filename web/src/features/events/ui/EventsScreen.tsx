'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { useClientRequestContext } from '@/shared/http/context.client'
import { useUpcomingEvents } from '../hooks/use-events-queries'
import { EventCalendar } from './EventCalendar'
import { EventCard } from './EventCard'

/**
 * How far ahead the page reads, the most `GET /events/upcoming` allows. One window feeds both the
 * list and the calendar, so a month the grid can reach within a year shows its anniversaries.
 */
export const UPCOMING_DAYS = 365

/**
 * The events page, spec § 7.8 (desktop): the upcoming list and the month calendar side by side,
 * both over `GET /events/upcoming`. Selecting a day in the grid filters the list.
 */
export function EventsScreen() {
  const t = useTranslations('events')
  const tCommon = useTranslations('common')
  const { context, ready, refreshAuth } = useClientRequestContext()
  const { data, isPending, isError, refetch } = useUpcomingEvents(UPCOMING_DAYS, {
    context,
    refreshAuth,
    enabled: ready,
  })
  const [selectedDay, setSelectedDay] = useState<string | null>(null)

  const events = data ?? []
  const shown = selectedDay ? events.filter((e) => e.nextOccurrence === selectedDay) : events

  let list
  if (!ready || isPending) {
    list = (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
    )
  } else if (isError) {
    list = (
      <div className="space-y-2">
        <p className="text-muted-foreground text-sm">{tCommon('error')}</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="text-primary text-sm font-medium underline"
        >
          {tCommon('retry')}
        </button>
      </div>
    )
  } else if (shown.length === 0) {
    list = (
      <p className="text-muted-foreground text-sm">
        {selectedDay ? t('no_events_on_day') : t('no_upcoming', { days: UPCOMING_DAYS })}
      </p>
    )
  } else {
    list = (
      <div className="space-y-2">
        {shown.map((event) => (
          <EventCard key={event.id} event={event} />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h1 className="text-foreground font-serif text-2xl">{t('page_title')}</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
        <section className="space-y-3 md:col-span-3">
          <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
            {t('upcoming')}
          </h2>
          {list}
        </section>
        <div className="md:col-span-2">
          <EventCalendar events={events} selectedDay={selectedDay} onSelectDay={setSelectedDay} />
        </div>
      </div>
    </div>
  )
}
