'use client'

import { EventCard } from './EventCard'
import { Skeleton } from '@/components/ui/skeleton'
import { useEvents } from '@/lib/hooks/useEvents'

export function EventListClient() {
  const { data, isLoading } = useEvents()
  const events = data?.pages.flatMap((p) => p.data) ?? []

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return <p className="text-muted-foreground text-sm">Chưa có sự kiện nào.</p>
  }

  return (
    <div className="space-y-2">
      {events.map((e) => (
        <EventCard key={e.id} event={e} />
      ))}
    </div>
  )
}
