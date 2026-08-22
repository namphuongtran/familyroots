/**
 * The one place `persons` query keys are built. `hooks/` reads a query and
 * `hooks/` invalidates a cache after a mutation — using two independently
 * hand-built key arrays for the same cache entry is exactly how invalidation
 * drifts, so every hook that touches a `persons` query key imports it from
 * here rather than writing `['persons', ...]` itself.
 *
 * Every key is scoped by `clanId` first, the same shape
 * `src/shared/http/clan-switch.test.tsx` proves for a plain `useQuery`: a
 * TanStack Query key is compared by value, so a key built from the active
 * clan refetches the moment `writeClanCookie` changes it — no manual
 * invalidation needed for a clan switch, only for a mutation inside the same
 * clan.
 *
 * `list`/`search`/`detail` deliberately exclude the cursor. The cursor is a
 * pagination position, owned by `useInfiniteQuery`'s own `pageParam`, not
 * part of *which* list is being asked for — including it in the key would
 * make every page of the same list a separate cache entry that never
 * invalidates together.
 */

import type { GetPersonQuery, ListPersonsQuery, SearchPersonsQuery } from '../api/persons-api'

type ClanId = string | null

const ROOT = 'persons' as const

function withoutCursor(query: ListPersonsQuery): Omit<ListPersonsQuery, 'cursor'> {
  const { cursor: _cursor, ...rest } = query
  return rest
}

export const personsKeys = {
  all: (clanId: ClanId) => [ROOT, clanId] as const,

  lists: (clanId: ClanId) => [...personsKeys.all(clanId), 'list'] as const,
  list: (clanId: ClanId, query: ListPersonsQuery) =>
    [...personsKeys.lists(clanId), withoutCursor(query)] as const,

  searches: (clanId: ClanId) => [...personsKeys.all(clanId), 'search'] as const,
  search: (clanId: ClanId, query: SearchPersonsQuery) =>
    [...personsKeys.searches(clanId), query] as const,

  details: (clanId: ClanId) => [...personsKeys.all(clanId), 'detail'] as const,
  detail: (clanId: ClanId, id: string, query: GetPersonQuery = {}) =>
    [...personsKeys.details(clanId), id, query] as const,
}
