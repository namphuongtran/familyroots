import type { EventCommandRepository } from '@/application/events/ports/event-command-repository'
import type { ClanEvent, EventCreateInput, EventUpdateInput } from '@/lib/types'

export function createEvent(
  repository: EventCommandRepository,
  input: EventCreateInput,
): Promise<ClanEvent> {
  return repository.create(input)
}

export function updateEvent(
  repository: EventCommandRepository,
  id: string,
  input: EventUpdateInput,
): Promise<ClanEvent> {
  return repository.update(id, input)
}

export function deleteEvent(
  repository: EventCommandRepository,
  id: string,
): Promise<void> {
  return repository.delete(id)
}
