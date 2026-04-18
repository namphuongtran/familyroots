import type { ClanEvent, EventCreateInput, EventUpdateInput } from '@/lib/types'

export interface EventCommandRepository {
  create(input: EventCreateInput): Promise<ClanEvent>
  update(id: string, input: EventUpdateInput): Promise<ClanEvent>
  delete(id: string): Promise<void>
}
