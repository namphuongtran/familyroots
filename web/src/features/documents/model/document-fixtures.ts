/** Wire-shaped documents fixtures, typed to the DTOs (themselves asserted against the generated contract). Tests only. */

import type { DocumentResponseDto, DocumentSummaryDto, SignedUploadDto } from './document-dto'

export const CLAN_ID = 'aaaaaaaa-0000-4000-8000-000000000001'
export const EXISTING_ID = 'dddddddd-0000-4000-8000-000000000001'
export const UPLOADED_ID = 'dddddddd-0000-4000-8000-000000000002'

export function documentSummaryDto(
  overrides: Partial<DocumentSummaryDto> = {},
): DocumentSummaryDto {
  return {
    id: EXISTING_ID,
    title: 'Gia phả chép tay 1925',
    document_type: 'certificate',
    mime_type: 'application/pdf',
    file_size_bytes: 1024,
    is_avatar: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function documentResponseDto(
  overrides: Partial<DocumentResponseDto> = {},
): DocumentResponseDto {
  return {
    ...documentSummaryDto(),
    clan_id: CLAN_ID,
    person_id: null,
    description: null,
    storage_path: `clans/${CLAN_ID}/documents/${EXISTING_ID}.pdf`,
    presigned_url: `https://storage.example/object/sign/family-roots-files/x.pdf?token=read`,
    presigned_url_expires_at: '2026-11-21T10:00:00Z',
    original_filename: 'gia-pha.pdf',
    taken_date: null,
    taken_place: null,
    created_by: '11111111-1111-4111-8111-111111111111',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function signedUploadDto(): SignedUploadDto {
  return {
    storage_path: `clans/${CLAN_ID}/uploads/0b9a3c1e-0000-4000-8000-000000000001.jpg`,
    upload_url:
      'https://storage.example/object/upload/sign/family-roots-files/clans/x/uploads/y.jpg?token=t1',
    token: 't1',
    expires_at: '2026-11-21T12:00:00Z',
  }
}
