import type { PersonQueryRepository } from '@/application/persons/ports/person-query-repository'
import type { Person } from '@/lib/types'
import { personsApi } from '@/lib/api/members'

// the legacy-component deletion trimmed this class to the one method the port still declares. See
// that port's own comment for which methods left and why `get` did not.

export class HttpPersonQueryRepository implements PersonQueryRepository {
  async get(id: string): Promise<Person> {
    return personsApi.get(id)
  }
}

export const personQueryRepository = new HttpPersonQueryRepository()
