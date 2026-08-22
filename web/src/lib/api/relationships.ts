import api from './axios'
import type {
  Marriage,
  MarriageCreateInput,
  MarriageUpdateInput,
  ParentChild,
  ParentChildCreateInput,
  ParentChildUpdateInput,
  ApiResponse,
} from '@/lib/types'

export const marriagesApi = {
  create: async (input: MarriageCreateInput): Promise<Marriage> => {
    const { data } = await api.post<ApiResponse<Marriage>>('/relationships/marriages', input)
    return data.data
  },

  get: async (id: string): Promise<Marriage> => {
    const { data } = await api.get<ApiResponse<Marriage>>(`/relationships/marriages/${id}`)
    return data.data
  },

  update: async (id: string, input: MarriageUpdateInput): Promise<Marriage> => {
    const { data } = await api.patch<ApiResponse<Marriage>>(`/relationships/marriages/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/relationships/marriages/${id}`),
}

export const parentChildApi = {
  create: async (input: ParentChildCreateInput): Promise<ParentChild> => {
    const { data } = await api.post<ApiResponse<ParentChild>>('/relationships/parent-child', input)
    return data.data
  },

  get: async (id: string): Promise<ParentChild> => {
    const { data } = await api.get<ApiResponse<ParentChild>>(`/relationships/parent-child/${id}`)
    return data.data
  },

  update: async (id: string, input: ParentChildUpdateInput): Promise<ParentChild> => {
    const { data } = await api.patch<ApiResponse<ParentChild>>(
      `/relationships/parent-child/${id}`,
      input,
    )
    return data.data
  },

  delete: (id: string) => api.delete(`/relationships/parent-child/${id}`),
}
