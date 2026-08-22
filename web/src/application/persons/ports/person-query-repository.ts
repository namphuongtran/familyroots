import type { Person } from '@/lib/types'

// S-033 trimmed this port to the one method `getPerson` (and, through it,
// `useMembers.ts`'s `usePerson`) still calls. `PersonsListQuery` and the
// `list`/`search`/`getMarriages`/`getParentChild`/`getTimeline`/
// `getDocuments`/`batchGet` methods it described are gone: nothing has
// called them since `src/components/members/{MemberList,MemberSearch,
// MemberDetailClient}.tsx` were deleted by this same seed.

export interface PersonQueryRepository {
  get(id: string): Promise<Person>
}
