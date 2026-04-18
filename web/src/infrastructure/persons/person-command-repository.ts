import type { PersonCommandRepository } from '@/application/persons/ports/person-command-repository'
import type { Person, PersonCreateInput, PersonUpdateInput } from '@/lib/types'
import { personsApi } from '@/lib/api/members'

export class HttpPersonCommandRepository implements PersonCommandRepository {
  create(input: PersonCreateInput): Promise<Person> {
    return personsApi.create(input)
  }

  update(id: string, input: PersonUpdateInput): Promise<Person> {
    return personsApi.update(id, input)
  }

  async delete(id: string): Promise<void> {
    await personsApi.delete(id)
  }
}

export const personCommandRepository = new HttpPersonCommandRepository()
