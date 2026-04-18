import type { Person, PersonCreateInput, PersonUpdateInput } from '@/lib/types'

export interface PersonCommandRepository {
  create(input: PersonCreateInput): Promise<Person>
  update(id: string, input: PersonUpdateInput): Promise<Person>
  delete(id: string): Promise<void>
}
