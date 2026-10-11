import api from './axios'
import type {
  DocumentResponse,
  DocumentSummary,
  DocumentUploadMeta,
  ApiResponse,
  CursorPage,
} from '@/lib/types'

// A document's bytes go from the browser straight to Supabase Storage (ADR-068), so Vercel's
// 4.5 MB body limit on the API no longer caps them (ADR-065 § 6). Three steps: the API signs
// one staged path after checking the declared name, type and size; the browser PUTs the file
// to the signed URL; the API confirms it, checking what Storage actually received. 50 MB is
// the domain's limit and the bucket's, and a larger file is refused here before any request.
// DocumentUpload reads the same number, so the screen and the transport cannot disagree.
export const MAX_UPLOAD_MB = 50
const MAX_FILE_SIZE_BYTES = MAX_UPLOAD_MB * 1024 * 1024

/** `POST /documents/uploads`'s `data`. `storage_path` goes back in the confirm call. */
interface SignedUpload {
  storage_path: string
  upload_url: string
  token: string
  expires_at: string
}

export const documentsApi = {
  list: async (params?: {
    cursor?: string
    limit?: number
    person_id?: string
  }): Promise<CursorPage<DocumentSummary>> => {
    const { data } = await api.get<{ data: DocumentSummary[] }>('/documents', { params })
    return {
      data: data.data,
      next_cursor: null,
      has_more: false,
    }
  },

  get: async (id: string): Promise<DocumentResponse> => {
    const { data } = await api.get<ApiResponse<DocumentResponse>>(`/documents/${id}`)
    return data.data
  },

  upload: async (file: File, meta: DocumentUploadMeta): Promise<DocumentResponse> => {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      throw new Error(`File size exceeds the ${MAX_UPLOAD_MB} MB limit`)
    }
    // A browser reports '' for a type it does not know. Sent as is, the API would answer with
    // a bare validation error; as octet-stream it answers invalid_mime_type, which names why.
    const contentType = file.type || 'application/octet-stream'

    const { data: signed } = await api.post<ApiResponse<SignedUpload>>('/documents/uploads', {
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
    })

    // Not through `api`: the request goes to Storage, which must not receive the session's
    // bearer token, and the signed URL is the whole authorization for this one upload.
    const put = await fetch(signed.data.upload_url, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': contentType },
    })
    if (!put.ok) {
      throw new Error(`Storage refused the upload (${put.status})`)
    }

    const { data } = await api.post<ApiResponse<DocumentResponse>>('/documents', {
      storage_path: signed.data.storage_path,
      original_filename: file.name,
      ...meta,
    })
    return data.data
  },

  delete: (id: string) => api.delete(`/documents/${id}`),
}
