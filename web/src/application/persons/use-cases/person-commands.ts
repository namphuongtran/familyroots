import type { PersonCommandRepository } from '@/application/persons/ports/person-command-repository'
import type { Person, PersonCreateInput, PersonUpdateInput } from '@/lib/types'

export function createPerson(
  repository: PersonCommandRepository,
  input: PersonCreateInput,
): Promise<Person> {
  return repository.create(input)
}

export function updatePerson(
  repository: PersonCommandRepository,
  id: string,
  input: PersonUpdateInput,
): Promise<Person> {
  return repository.update(id, input)
}

export function deletePerson(
  repository: PersonCommandRepository,
  id: string,
): Promise<void> {
  return repository.delete(id)
}
