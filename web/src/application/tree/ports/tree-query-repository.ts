import type {
  RelationshipPath,
  TreeApiResponse,
} from '@/lib/types'

export interface TreeQueryRepository {
  getFullTree(params?: {
    root_person_id?: string
    max_generations?: number
  }): Promise<TreeApiResponse>
  getSubtree(rootId: string, maxGenerations?: number): Promise<TreeApiResponse>
  getAncestors(personId: string, maxGenerations?: number): Promise<TreeApiResponse>
  getRelationshipPath(fromId: string, toId: string): Promise<RelationshipPath>
}