import { getTranslations } from 'next-intl/server'
import { EventCalendar } from '@/components/events/EventCalendar'
import { EventCard } from '@/components/events/EventCard'

// EventsPage renders both the upcoming list and the calendar side by side.
// Data fetching happens client-side via useEvents.
export default async function EventsPage() {
  const t = await getTranslations('events')

  return (
    <div className="space-y-4">
      <h1 className="text-foreground font-serif text-2xl">{t('page_title')}</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
        {/* Upcoming events column */}
        <div className="space-y-3 md:col-span-3">
          <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
            {t('upcoming')}
          </h2>
          <EventListClient />
        </div>
        {/* Calendar column */}
        <div className="md:col-span-2">
          <EventCalendar />
        </div>
      </div>
    </div>
  )
}

import { EventListClient } from '@/components/events/EventListClient'
