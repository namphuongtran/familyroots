import type { EventCommandRepository } from '@/application/events/ports/event-command-repository'
import type { ClanEvent, EventCreateInput, EventUpdateInput } from '@/lib/types'
import { eventsApi } from '@/lib/api/events'

export class HttpEventCommandRepository implements EventCommandRepository {
  create(input: EventCreateInput): Promise<ClanEvent> {
    return eventsApi.create(input)
  }

  update(id: string, input: EventUpdateInput): Promise<ClanEvent> {
    return eventsApi.update(id, input)
  }

  async delete(id: string): Promise<void> {
    await eventsApi.delete(id)
  }
}

export const eventCommandRepository = new HttpEventCommandRepository()
