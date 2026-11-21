/**
 * The `documents` repository: fetch (`../api/documents-api`) → parse (`../model/document-dto`) →
 * map to `@/domain/document/document`. Returns domain values only.
 */

import {
  exceedsUploadLimit,
  MAX_UPLOAD_MB,
  type DocumentDetail,
  type DocumentSummary,
  type DocumentType,
} from '@/domain/document/document'
import { unwrapData, unwrapPage, type Page } from '@/shared/http/envelope'
import { ApiError, INVALID_CURSOR_CODE } from '@/shared/http/errors'
import * as api from '../api/documents-api'
import type { DocumentsApiCallOptions, ListDocumentsQuery } from '../api/documents-api'
import {
  documentResponseDtoSchema,
  documentSummaryDtoSchema,
  signedUploadDtoSchema,
  toDocumentDetail,
  toDocumentSummary,
} from '../model/document-dto'

export type { DocumentsApiCallOptions, ListDocumentsQuery }

const parseSummary = (raw: unknown) => toDocumentSummary(documentSummaryDtoSchema.parse(raw))
const parseDetail = (raw: unknown) => toDocumentDetail(documentResponseDtoSchema.parse(raw))

/** Thrown before any request when a file is over the limit. */
export class FileTooLargeError extends Error {
  readonly maxMb = MAX_UPLOAD_MB
  constructor() {
    super(`File size exceeds the ${MAX_UPLOAD_MB} MB limit`)
    this.name = 'FileTooLargeError'
  }
}

/** Storage refused the PUT (step 2). Nothing was confirmed. */
export class StorageUploadError extends Error {
  constructor(readonly status: number) {
    super(`Storage refused the upload (${status})`)
    this.name = 'StorageUploadError'
  }
}

/** `GET /documents`. On `400 invalid_cursor` it drops the cursor and reads page one, as persons does. */
export async function listDocuments(
  query: ListDocumentsQuery,
  options: DocumentsApiCallOptions,
): Promise<Page<DocumentSummary>> {
  try {
    return unwrapPage(await api.listDocuments(query, options), parseSummary)
  } catch (error) {
    if (error instanceof ApiError && error.code === INVALID_CURSOR_CODE && query.cursor != null) {
      return unwrapPage(await api.listDocuments({ ...query, cursor: null }, options), parseSummary)
    }
    throw error
  }
}

/** `GET /documents/{id}`, with a freshly minted signed URL. */
export async function getDocument(
  id: string,
  options: DocumentsApiCallOptions,
): Promise<DocumentDetail> {
  return unwrapData(await api.getDocument(id, options), parseDetail)
}

export interface UploadDocumentInput {
  file: File
  title: string
  documentType: DocumentType
  personId?: string | null
}

/**
 * ADR-068's two API calls with Storage between them: sign, PUT the bytes to Storage, confirm. The
 * file never travels to the API, whose host refuses a body over 4.5 MB with a 413 that carries no
 * envelope (ADR-065). A file over the limit is refused before any request.
 */
export async function uploadDocument(
  input: UploadDocumentInput,
  options: DocumentsApiCallOptions,
): Promise<DocumentDetail> {
  const { file } = input
  if (exceedsUploadLimit(file.size)) throw new FileTooLargeError()
  // A browser reports '' for a type it does not know. Sent as is, the API would answer with a
  // bare validation error; as octet-stream it answers invalid_mime_type, which names why.
  const contentType = file.type || 'application/octet-stream'

  const signed = unwrapData(
    await api.signUpload(
      { filename: file.name, content_type: contentType, size_bytes: file.size },
      options,
    ),
    (raw) => signedUploadDtoSchema.parse(raw),
  )

  const status = await api.putToStorage(signed.upload_url, file, contentType, options)
  if (status < 200 || status >= 300) throw new StorageUploadError(status)

  return unwrapData(
    await api.confirmUpload(
      {
        storage_path: signed.storage_path,
        original_filename: file.name,
        title: input.title,
        document_type: input.documentType,
        person_id: input.personId ?? undefined,
      },
      options,
    ),
    parseDetail,
  )
}

/** `DELETE /documents/{id}` — soft delete (ADR-019); the row disappears from every read. */
export async function deleteDocument(id: string, options: DocumentsApiCallOptions): Promise<void> {
  await api.deleteDocument(id, options)
}
