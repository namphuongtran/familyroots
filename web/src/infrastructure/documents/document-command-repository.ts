import type { DocumentCommandRepository } from '@/application/documents/ports/document-command-repository'
import type { DocumentResponse, DocumentUploadMeta } from '@/lib/types'
import { documentsApi } from '@/lib/api/documents'

export class HttpDocumentCommandRepository implements DocumentCommandRepository {
  upload(file: File, meta: DocumentUploadMeta): Promise<DocumentResponse> {
    return documentsApi.upload(file, meta)
  }

  async delete(id: string): Promise<void> {
    await documentsApi.delete(id)
  }
}

export const documentCommandRepository = new HttpDocumentCommandRepository()
