import type {
  MarriageCommandRepository,
  ParentChildCommandRepository,
} from '@/application/relationships/ports/relationship-command-repository'
import type {
  MarriageCreateInput,
  MarriageUpdateInput,
  ParentChildCreateInput,
  ParentChildUpdateInput,
} from '@/lib/types'

export function createMarriage(repository: MarriageCommandRepository, input: MarriageCreateInput) {
  return repository.create(input)
}

export function updateMarriage(
  repository: MarriageCommandRepository,
  id: string,
  input: MarriageUpdateInput,
) {
  return repository.update(id, input)
}

export function deleteMarriage(repository: MarriageCommandRepository, id: string) {
  return repository.delete(id)
}

export function createParentChild(
  repository: ParentChildCommandRepository,
  input: ParentChildCreateInput,
) {
  return repository.create(input)
}

export function updateParentChild(
  repository: ParentChildCommandRepository,
  id: string,
  input: ParentChildUpdateInput,
) {
  return repository.update(id, input)
}

export function deleteParentChild(repository: ParentChildCommandRepository, id: string) {
  return repository.delete(id)
}
