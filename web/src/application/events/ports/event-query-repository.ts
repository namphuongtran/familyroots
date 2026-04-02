import type {
  ClanEvent,
  CursorPage,
  UpcomingEvent,
} from '@/lib/types'

export interface EventQueryRepository {
  list(params?: { cursor?: string; limit?: number }): Promise<CursorPage<ClanEvent>>
  getUpcoming(days?: number): Promise<UpcomingEvent[]>
  get(id: string): Promise<ClanEvent>
}