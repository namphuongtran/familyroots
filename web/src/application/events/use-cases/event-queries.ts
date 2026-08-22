import type { EventQueryRepository } from '@/application/events/ports/event-query-repository'

export function listEvents(
  repository: EventQueryRepository,
  params?: { cursor?: string; limit?: number },
) {
  return repository.list(params)
}

export function getUpcomingEvents(repository: EventQueryRepository, days = 30) {
  return repository.getUpcoming(days)
}

export function getEvent(repository: EventQueryRepository, id: string) {
  return repository.get(id)
}
