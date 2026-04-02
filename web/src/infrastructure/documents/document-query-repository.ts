import type { DocumentQueryRepository } from '@/application/documents/ports/document-query-repository'
import type {
  CursorPage,
  DocumentResponse,
  DocumentSummary,
} from '@/lib/types'
import { documentsApi } from '@/lib/api/documents'

export class HttpDocumentQueryRepository implements DocumentQueryRepository {
  async list(params?: {
    cursor?: string
    limit?: number
    person_id?: string
  }): Promise<CursorPage<DocumentSummary>> {
    return documentsApi.list(params)
  }

  async get(id: string): Promise<DocumentResponse> {
    return documentsApi.get(id)
  }
}

export const documentQueryRepository = new HttpDocumentQueryRepository()