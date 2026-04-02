import type { DocumentQueryRepository } from '@/application/documents/ports/document-query-repository'

export function listDocuments(
  repository: DocumentQueryRepository,
  params?: {
    cursor?: string
    limit?: number
    person_id?: string
  },
) {
  return repository.list(params)
}

export function getDocument(repository: DocumentQueryRepository, id: string) {
  return repository.get(id)
}