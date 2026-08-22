import type { EventQueryRepository } from '@/application/events/ports/event-query-repository'
import type { ClanEvent, CursorPage, UpcomingEvent } from '@/lib/types'
import { eventsApi } from '@/lib/api/events'

export class HttpEventQueryRepository implements EventQueryRepository {
  async list(params?: { cursor?: string; limit?: number }): Promise<CursorPage<ClanEvent>> {
    return eventsApi.list(params)
  }

  async getUpcoming(days = 30): Promise<UpcomingEvent[]> {
    return eventsApi.getUpcoming(days)
  }

  async get(id: string): Promise<ClanEvent> {
    return eventsApi.get(id)
  }
}

export const eventQueryRepository = new HttpEventQueryRepository()
