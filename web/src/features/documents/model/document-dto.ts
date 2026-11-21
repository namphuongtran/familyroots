/**
 * Zod DTOs for the documents contract, each constrained to `src/generated/api-types.ts` by an
 * `assert…MatchesGenerated` function whose body is `return dto`, plus the mappers into
 * `@/domain/document/document`. Same pattern as `features/events/model/event-dto.ts`.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { DocumentDetail, DocumentSummary } from '@/domain/document/document'

type Generated = components['schemas']

const nullableString = z.string().nullable().optional()
const nullableNumber = z.number().nullable().optional()

/** Mirrors `components["schemas"]["DocumentSummary"]`. */
export const documentSummaryDtoSchema = z.object({
  id: z.string(),
  title: z.string(),
  document_type: z.string(),
  mime_type: nullableString,
  file_size_bytes: nullableNumber,
  is_avatar: z.boolean(),
  created_at: z.string(),
})
export type DocumentSummaryDto = z.infer<typeof documentSummaryDtoSchema>

export function assertDocumentSummaryDtoMatchesGenerated(
  dto: DocumentSummaryDto,
): Generated['DocumentSummary'] {
  return dto
}

/** Mirrors `components["schemas"]["DocumentResponse"]`. */
export const documentResponseDtoSchema = documentSummaryDtoSchema.extend({
  clan_id: z.string(),
  person_id: nullableString,
  description: nullableString,
  storage_path: z.string(),
  presigned_url: nullableString,
  presigned_url_expires_at: nullableString,
  original_filename: nullableString,
  taken_date: nullableString,
  taken_place: nullableString,
  created_by: z.string(),
  updated_at: z.string(),
})
export type DocumentResponseDto = z.infer<typeof documentResponseDtoSchema>

export function assertDocumentResponseDtoMatchesGenerated(
  dto: DocumentResponseDto,
): Generated['DocumentResponse'] {
  return dto
}

/** Mirrors `components["schemas"]["SignedUploadResponse"]`. */
export const signedUploadDtoSchema = z.object({
  storage_path: z.string(),
  upload_url: z.string(),
  token: z.string(),
  expires_at: z.string(),
})
export type SignedUploadDto = z.infer<typeof signedUploadDtoSchema>

export function assertSignedUploadDtoMatchesGenerated(
  dto: SignedUploadDto,
): Generated['SignedUploadResponse'] {
  return dto
}

export function toDocumentSummary(dto: DocumentSummaryDto): DocumentSummary {
  return {
    id: dto.id,
    title: dto.title,
    documentType: dto.document_type,
    mimeType: dto.mime_type ?? null,
    fileSizeBytes: dto.file_size_bytes ?? null,
    isAvatar: dto.is_avatar,
    createdAt: dto.created_at,
  }
}

export function toDocumentDetail(dto: DocumentResponseDto): DocumentDetail {
  return {
    ...toDocumentSummary(dto),
    personId: dto.person_id ?? null,
    description: dto.description ?? null,
    originalFilename: dto.original_filename ?? null,
    presignedUrl: dto.presigned_url ?? null,
    presignedUrlExpiresAt: dto.presigned_url_expires_at ?? null,
  }
}
