import api from './axios'
import type { Relationship, RelationshipCreateInput, RelationshipUpdateInput, ApiResponse } from '@/lib/types'

export const relationshipsApi = {
  create: async (input: RelationshipCreateInput): Promise<Relationship> => {
    const { data } = await api.post<ApiResponse<Relationship> & { warning?: string }>(
      '/relationships',
      input,
    )
    return data.data
  },

  get: async (id: string): Promise<Relationship> => {
    const { data } = await api.get<ApiResponse<Relationship>>(`/relationships/${id}`)
    return data.data
  },

  update: async (id: string, input: RelationshipUpdateInput): Promise<Relationship> => {
    const { data } = await api.patch<ApiResponse<Relationship>>(`/relationships/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/relationships/${id}`),
}
