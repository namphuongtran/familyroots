import api from './axios'
import type {
  TreeApiResponse,
  TreeAncestorsResponse,
  RelationshipPath,
  ApiResponse,
} from '@/lib/types'

export const treeApi = {
  getFullTree: async (params?: {
    root_person_id?: string
    max_generations?: number
  }): Promise<TreeApiResponse> => {
    const { data } = await api.get<ApiResponse<TreeApiResponse>>('/tree', { params })
    return data.data
  },

  getSubtree: async (rootId: string, maxGenerations = 5): Promise<TreeApiResponse> => {
    const { data } = await api.get<ApiResponse<TreeApiResponse>>(`/tree/subtree/${rootId}`, {
      params: { max_generations: maxGenerations },
    })
    return data.data
  },

  getAncestors: async (personId: string, maxGenerations = 10): Promise<TreeAncestorsResponse> => {
    const { data } = await api.get<ApiResponse<TreeAncestorsResponse>>(
      `/tree/ancestors/${personId}`,
      {
        params: { max_generations: maxGenerations },
      },
    )
    return data.data
  },

  getRelationshipPath: async (fromId: string, toId: string): Promise<RelationshipPath> => {
    const { data } = await api.get<ApiResponse<RelationshipPath>>('/tree/path', {
      params: { from_id: fromId, to_id: toId },
    })
    return data.data
  },
}
