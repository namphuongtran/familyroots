'use client'

/**
 * One batch lookup of the people at the other end of a set of edges, through the persons
 * slice's public surface. Keyed by clan and the sorted ids, so two components asking for the
 * same set share one request, and a persons mutation that invalidates `personsKeys.all` reaches
 * it too. Moved here from `RelationshipsAside` when the editor sheet (#328) needed the same read.
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Person } from '@/domain/person/person'
import type { RequestContext } from '@/shared/http/request-context'
import { batchGetPersons, personsKeys } from '@/features/persons'

export function useRelatedPeople(
  ids: readonly string[],
  options: {
    context: RequestContext
    refreshAuth?: () => Promise<RequestContext | null>
    enabled: boolean
  },
): Map<string, Person> {
  const { context, refreshAuth, enabled } = options
  const sortedKey = [...ids].sort().join(',')
  const query = useQuery({
    queryKey: [...personsKeys.all(context.clanId), 'batch', sortedKey],
    queryFn: ({ signal }) =>
      batchGetPersons({ ids: [...ids], profile: 'summary' }, { context, refreshAuth, signal }),
    enabled: enabled && ids.length > 0,
  })
  return useMemo(() => {
    const map = new Map<string, Person>()
    for (const p of query.data?.items ?? []) map.set(p.id, p)
    return map
  }, [query.data])
}
