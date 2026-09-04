import type { Person } from '@/lib/types'
import type { PersonQueryRepository } from '@/application/persons/ports/person-query-repository'

// the legacy-component deletion deleted `listPersons`, `searchPersons`, `getPersonMarriages`,
// `getPersonParentChild`, `getPersonTimeline`, `getPersonDocuments`, and
// `batchGetPersons` here: their sole caller, `src/lib/hooks/useMembers.ts`'s
// legacy hooks, was deleted with them. `getPerson` stays because
// `useMembers.ts`'s `usePerson` still calls it — see that file's header
// comment for who still needs `usePerson` and why.

export async function getPerson(repository: PersonQueryRepository, id: string): Promise<Person> {
  return repository.get(id)
}
