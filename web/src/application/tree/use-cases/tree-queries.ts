import type { TreeQueryRepository } from '@/application/tree/ports/tree-query-repository'

export function getFullTree(
  repository: TreeQueryRepository,
  params?: {
    root_person_id?: string
    max_generations?: number
  },
) {
  return repository.getFullTree(params)
}

export function getSubtree(repository: TreeQueryRepository, rootId: string, maxGenerations = 5) {
  return repository.getSubtree(rootId, maxGenerations)
}

export function getAncestors(
  repository: TreeQueryRepository,
  personId: string,
  maxGenerations = 10,
) {
  return repository.getAncestors(personId, maxGenerations)
}

export function getRelationshipPath(repository: TreeQueryRepository, fromId: string, toId: string) {
  return repository.getRelationshipPath(fromId, toId)
}
