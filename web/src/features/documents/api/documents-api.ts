/**
 * Transport for docs/contracts/rest-documents-api.md. Calls `apiFetch` and nothing else, except the
 * one request that does not go to the API: the PUT of a file's bytes to Storage (ADR-068). No
 * React, no parsing. Every function returns the raw body; the repository parses and maps it.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'
import type { components } from '@/generated/api-types'

export type DocumentsApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

export interface ListDocumentsQuery {
  /** Opaque — pass back exactly what a previous page's `meta.cursor` returned. */
  cursor?: string | null
  limit?: number
  person_id?: string
}

export type SignUploadRequest = components['schemas']['SignUploadRequest']
export type DocumentCreateRequest = components['schemas']['DocumentCreateRequest']

/** `GET /documents` — cursor-paginated summaries, no URL. */
export function listDocuments(
  query: ListDocumentsQuery,
  options: DocumentsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/documents', {
    ...options,
    method: 'GET',
    query: { cursor: query.cursor, limit: query.limit, person_id: query.person_id },
  })
}

/** `GET /documents/{id}` — the detail, with a freshly minted signed URL. */
export function getDocument(id: string, options: DocumentsApiCallOptions): Promise<unknown> {
  return apiFetch(`/documents/${encodeURIComponent(id)}`, { ...options, method: 'GET' })
}

/** `POST /documents/uploads` — step 1: sign one staged path. Carries no file. */
export function signUpload(
  body: SignUploadRequest,
  options: DocumentsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/documents/uploads', { ...options, method: 'POST', body })
}

/**
 * Step 2: `PUT upload_url` to Storage, not the API. No `Authorization` header and no clan header:
 * the signed URL is the whole authorization for this one upload, and Storage must not receive the
 * session's token. Returns the status; the repository decides what a refusal means.
 */
export async function putToStorage(
  uploadUrl: string,
  file: Blob,
  contentType: string,
  options: Pick<DocumentsApiCallOptions, 'fetchImpl' | 'signal'>,
): Promise<number> {
  const doFetch = options.fetchImpl ?? fetch
  const response = await doFetch(
    new Request(uploadUrl, {
      method: 'PUT',
      body: file,
      headers: { 'content-type': contentType },
      signal: options.signal,
    }),
  )
  return response.status
}

/** `POST /documents` — step 3: confirm the staged path as a document. JSON, never the file. */
export function confirmUpload(
  body: DocumentCreateRequest,
  options: DocumentsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/documents', { ...options, method: 'POST', body })
}

/** `DELETE /documents/{id}` (admin) — a soft delete (ADR-019). */
export function deleteDocument(id: string, options: DocumentsApiCallOptions): Promise<unknown> {
  return apiFetch(`/documents/${encodeURIComponent(id)}`, { ...options, method: 'DELETE' })
}
