/**
 * Public surface of the `documents` slice. `cross-feature-only-via-index` requires every other
 * feature, and `src/app`, to import this slice through this file. The raw `api/` transport is not
 * re-exported, as in persons, tree and events: callers get parsed domain values only.
 */

export type { DocumentDetail, DocumentSummary } from '@/domain/document/document'
export { MAX_UPLOAD_MB } from '@/domain/document/document'

export type {
  DocumentsApiCallOptions,
  ListDocumentsQuery,
  UploadDocumentInput,
} from './server/documents-repository'
export {
  deleteDocument,
  FileTooLargeError,
  getDocument,
  listDocuments,
  StorageUploadError,
  uploadDocument,
} from './server/documents-repository'
export { documentsKeys } from './server/query-keys'

export type { DocumentsQueryOptions } from './hooks/use-documents-queries'
export {
  useDeleteDocument,
  useDocumentsList,
  useOpenDocument,
  useUploadDocument,
} from './hooks/use-documents-queries'

export { DocumentsScreen } from './ui/DocumentsScreen'
