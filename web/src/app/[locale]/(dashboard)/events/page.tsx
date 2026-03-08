import { getTranslations } from 'next-intl/server'
import { EventCalendar } from '@/components/events/EventCalendar'
import { EventCard } from '@/components/events/EventCard'

// EventsPage renders both the upcoming list and the calendar side by side.
// Data fetching happens client-side via useEvents.
export default async function EventsPage() {
  const t = await getTranslations('events')

  return (
    <div className="space-y-4">
      <h1 className="font-serif text-2xl text-gray-800">{t('page_title')}</h1>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {/* Upcoming events column */}
        <div className="md:col-span-3 space-y-3">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
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
