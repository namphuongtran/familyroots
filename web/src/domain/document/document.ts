/**
 * The documents read model (docs/contracts/rest-documents-api.md) in domain shape: camelCase, and
 * every "key absent" normalised to `null`. Types and the upload limit only.
 *
 * A document's file lives in a private Storage bucket. The list carries no URL; the one way to
 * read the file is `presignedUrl` on a detail read, which expires at `presignedUrlExpiresAt`
 * (one hour, ADR-019 / storage.md). It is never cached past that.
 */

/** `photo`, `id_document`, `certificate`, `audio`, `video` or `other`. */
export type DocumentType = string

/** One row of `GET /documents`. */
export interface DocumentSummary {
  id: string
  title: string
  documentType: DocumentType
  mimeType: string | null
  fileSizeBytes: number | null
  isAvatar: boolean
  /** ISO timestamp, UTC. */
  createdAt: string
}

/** `GET /documents/{id}` and the confirm call's `data`. */
export interface DocumentDetail extends DocumentSummary {
  personId: string | null
  description: string | null
  originalFilename: string | null
  /** Short-lived signed URL into the private bucket, or null when the backend minted none. */
  presignedUrl: string | null
  presignedUrlExpiresAt: string | null
}

/**
 * The upload limit, in MB: the domain's and the bucket's, `MAX_UPLOAD_SIZE_MB` on the backend
 * (ADR-068). The screen refuses a larger file before any request, so this must never exceed the
 * backend's; a higher number here lets through a file the backend refuses at signing.
 */
export const MAX_UPLOAD_MB = 50
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

export function exceedsUploadLimit(sizeBytes: number): boolean {
  return sizeBytes > MAX_UPLOAD_BYTES
}

/**
 * The content types `POST /documents/uploads` approves, as the file picker's `accept`. A type
 * outside this list is refused by the backend with `422 invalid_mime_type`.
 */
export const APPROVED_UPLOAD_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/pdf',
  'audio/mpeg',
  'audio/wav',
  'video/mp4',
  'video/quicktime',
] as const
