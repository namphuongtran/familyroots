import type { DocumentResponse, DocumentUploadMeta } from '@/lib/types'

export interface DocumentCommandRepository {
  upload(file: File, meta: DocumentUploadMeta): Promise<DocumentResponse>
  delete(id: string): Promise<void>
}
