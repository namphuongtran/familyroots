// Document types — aligned with backend DocumentResponse / DocumentSummary

export type DocumentType =
  | 'photo'
  | 'id_document'
  | 'certificate'
  | 'audio'
  | 'video'
  | 'other'

export interface DocumentResponse {
  id: string
  clan_id: string
  member_id?: string
  title: string
  document_type: DocumentType
  storage_path: string
  presigned_url?: string
  presigned_url_expires_at?: string
  file_size_bytes?: number
  mime_type?: string
  original_filename?: string
  taken_date?: string
  taken_place?: string
  is_avatar: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface DocumentSummary {
  id: string
  title: string
  document_type: DocumentType
  mime_type?: string
  file_size_bytes?: number
  file_url: string
  is_avatar: boolean
  created_at: string
}

export interface DocumentUploadMeta {
  member_id?: string
  title: string
  document_type: DocumentType
  description?: string
  taken_date?: string
  taken_place?: string
}
