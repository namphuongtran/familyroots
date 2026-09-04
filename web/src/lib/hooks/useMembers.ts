'use client'

/**
 * the legacy-component deletion trimmed this file to the two exports that still have a real,
 * out-of-scope importer, and deleted everything else: `usePersons`,
 * `usePersonSearch`, `usePersonMarriages`, `usePersonParentChild`,
 * `usePersonTimeline`, `usePersonsBatch`, and `usePersonMutations` had zero
 * importers left once `src/components/members/{MemberList,MemberSearch,
 * MemberDetailClient,MemberForm}.tsx` — their only callers — were deleted
 * with this same seed.
 *
 * What is left, and why it cannot go with the rest:
 * - `usePerson` is still called by `src/components/family-tree/MemberSidebar.tsx`
 *   (the tree feature, its own future slice, out of scope here).
 * - `personKeys.marriages`/`personKeys.parentChild` are still read by
 *   `src/lib/hooks/useRelationships.ts` (the relationships feature, also its
 *   own future slice) purely as invalidation keys — it never calls a query
 *   function from this file, only builds the same cache key `usePerson`
 *   would use.
 *
 * This is the same shape the legacy-transport deletion left `src/lib/api/axios.ts` in: a shared
 * legacy file survives, trimmed to what a *different* slice still needs,
 * until that slice's own deletion seed lands. See `web/CLAUDE.md`,
 * "Migration notes", for the axios precedent this one repeats.
 */

import { useQuery } from '@tanstack/react-query'
import { getPerson } from '@/application/persons/use-cases/person-queries'
import { personQueryRepository } from '@/infrastructure/persons/person-query-repository'

export const personKeys = {
  all: ['persons'] as const,
  details: () => [...personKeys.all, 'detail'] as const,
  detail: (id: string) => [...personKeys.details(), id] as const,
  marriages: (id: string) => [...personKeys.detail(id), 'marriages'] as const,
  parentChild: (id: string) => [...personKeys.detail(id), 'parent-child'] as const,
}

/** Single person detail */
export function usePerson(id: string | undefined) {
  return useQuery({
    queryKey: personKeys.detail(id!),
    queryFn: () => getPerson(personQueryRepository, id!),
    enabled: !!id,
  })
}
