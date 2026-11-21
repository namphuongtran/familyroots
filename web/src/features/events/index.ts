/**
 * Public surface of the `events` slice. `cross-feature-only-via-index` requires every other
 * feature, and `src/app`, to import this slice through this file. The raw `api/` transport is not
 * re-exported, as in persons and tree: callers get parsed domain values only.
 */

export type { UpcomingEvent } from '@/domain/event/event'

export type { EventsApiCallOptions, GetUpcomingEventsQuery } from './server/events-repository'
export { getUpcomingEvents } from './server/events-repository'
export { eventsKeys } from './server/query-keys'

export type { EventsQueryOptions } from './hooks/use-events-queries'
export { useUpcomingEvents } from './hooks/use-events-queries'

export { EventsScreen } from './ui/EventsScreen'
