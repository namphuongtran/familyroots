import api from './axios'
import type {
  Marriage, MarriageCreateInput, MarriageUpdateInput,
  ParentChild, ParentChildCreateInput, ParentChildUpdateInput,
  ApiResponse,
} from '@/lib/types'

export const marriagesApi = {
  create: async (input: MarriageCreateInput): Promise<Marriage> => {
    const { data } = await api.post<ApiResponse<Marriage>>('/marriages', input)
    return data.data
  },

  get: async (id: string): Promise<Marriage> => {
    const { data } = await api.get<ApiResponse<Marriage>>(`/marriages/${id}`)
    return data.data
  },

  update: async (id: string, input: MarriageUpdateInput): Promise<Marriage> => {
    const { data } = await api.patch<ApiResponse<Marriage>>(`/marriages/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/marriages/${id}`),
}

export const parentChildApi = {
  create: async (input: ParentChildCreateInput): Promise<ParentChild> => {
    const { data } = await api.post<ApiResponse<ParentChild>>('/parent-child', input)
    return data.data
  },

  get: async (id: string): Promise<ParentChild> => {
    const { data } = await api.get<ApiResponse<ParentChild>>(`/parent-child/${id}`)
    return data.data
  },

  update: async (id: string, input: ParentChildUpdateInput): Promise<ParentChild> => {
    const { data } = await api.patch<ApiResponse<ParentChild>>(`/parent-child/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/parent-child/${id}`),
}
