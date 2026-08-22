import type { CursorPage, DocumentResponse, DocumentSummary } from '@/lib/types'

export interface DocumentQueryRepository {
  list(params?: {
    cursor?: string
    limit?: number
    person_id?: string
  }): Promise<CursorPage<DocumentSummary>>
  get(id: string): Promise<DocumentResponse>
}
