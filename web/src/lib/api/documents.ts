import api from './axios'
import type { DocumentResponse, DocumentSummary, DocumentUploadMeta, ApiResponse, CursorPage } from '@/lib/types'

const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024 // 50 MB

export const documentsApi = {
  list: async (params?: { cursor?: string; limit?: number; member_id?: string }): Promise<CursorPage<DocumentSummary>> => {
    const { data } = await api.get<CursorPage<DocumentSummary>>('/documents', { params })
    return data
  },

  get: async (id: string): Promise<DocumentResponse> => {
    const { data } = await api.get<ApiResponse<DocumentResponse>>(`/documents/${id}`)
    return data.data
  },

  upload: async (file: File, meta: DocumentUploadMeta): Promise<DocumentResponse> => {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      throw new Error(`File size exceeds the 50 MB limit`)
    }

    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', meta.title)
    formData.append('document_type', meta.document_type)
    if (meta.member_id) formData.append('member_id', meta.member_id)
    if (meta.description) formData.append('description', meta.description)
    if (meta.taken_date) formData.append('taken_date', meta.taken_date)
    if (meta.taken_place) formData.append('taken_place', meta.taken_place)

    const { data } = await api.post<ApiResponse<DocumentResponse>>('/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.data
  },

  delete: (id: string) => api.delete(`/documents/${id}`),
}
