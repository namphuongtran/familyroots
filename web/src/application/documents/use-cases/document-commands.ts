import type { DocumentCommandRepository } from '@/application/documents/ports/document-command-repository'
import type { DocumentResponse, DocumentUploadMeta } from '@/lib/types'

export function uploadDocument(
  repository: DocumentCommandRepository,
  file: File,
  meta: DocumentUploadMeta,
): Promise<DocumentResponse> {
  return repository.upload(file, meta)
}

export function deleteDocument(
  repository: DocumentCommandRepository,
  id: string,
): Promise<void> {
  return repository.delete(id)
}
