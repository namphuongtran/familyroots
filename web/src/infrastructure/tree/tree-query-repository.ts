import type { TreeQueryRepository } from '@/application/tree/ports/tree-query-repository'
import type {
  RelationshipPath,
  TreeApiResponse,
} from '@/lib/types'
import { treeApi } from '@/lib/api/tree'

export class HttpTreeQueryRepository implements TreeQueryRepository {
  async getFullTree(params?: {
    root_person_id?: string
    max_generations?: number
  }): Promise<TreeApiResponse> {
    return treeApi.getFullTree(params)
  }

  async getSubtree(rootId: string, maxGenerations = 5): Promise<TreeApiResponse> {
    return treeApi.getSubtree(rootId, maxGenerations)
  }

  async getAncestors(personId: string, maxGenerations = 10): Promise<TreeApiResponse> {
    return treeApi.getAncestors(personId, maxGenerations)
  }

  async getRelationshipPath(fromId: string, toId: string): Promise<RelationshipPath> {
    return treeApi.getRelationshipPath(fromId, toId)
  }
}

export const treeQueryRepository = new HttpTreeQueryRepository()