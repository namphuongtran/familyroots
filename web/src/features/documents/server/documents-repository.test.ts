import { describe, expect, it, vi } from 'vitest'
import type { FetchLike } from '@/shared/http/api-client'
import type { RequestContext } from '@/shared/http/request-context'
import {
  documentResponseDto,
  documentSummaryDto,
  signedUploadDto,
  UPLOADED_ID,
} from '../model/document-fixtures'
import {
  FileTooLargeError,
  listDocuments,
  StorageUploadError,
  uploadDocument,
} from './documents-repository'

/**
 * The upload is three requests (ADR-068): sign at the API, PUT the bytes to Storage, confirm at
 * the API. Each case reads the requests that left, through the one fetch seam, in order, with
 * what each carried. The outcome that matters is where the bytes go: no request to the API may
 * carry the file, because the API's host refuses a body over 4.5 MB with an envelope-less 413.
 */

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }
const MB = 1024 * 1024
const SIGNED = signedUploadDto()

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function fileOf(bytes: number, type = 'image/jpeg'): File {
  const file = new File(['x'], 'gia-pha.jpg', { type })
  Object.defineProperty(file, 'size', { value: bytes })
  return file
}

interface Sent {
  target: string
  headers: Headers
  body: string | null
}

function recordingFetch(storageStatus = 200) {
  const sent: Sent[] = []
  const fetchImpl = vi.fn<FetchLike>(async (request) => {
    const url = new URL(request.url)
    const isStorage = url.origin === new URL(SIGNED.upload_url).origin
    const body = request.method === 'PUT' ? `<file>` : request.body ? await request.text() : null
    sent.push({
      target: `${request.method} ${isStorage ? request.url : url.pathname.replace(/^.*\/api\/v1/, '')}`,
      headers: request.headers,
      body,
    })
    if (isStorage) return new Response(null, { status: storageStatus })
    if (url.pathname.endsWith('/documents/uploads')) return json({ data: SIGNED })
    return json({ data: documentResponseDto({ id: UPLOADED_ID, title: 'Gia phả' }) }, 201)
  })
  return { sent, fetchImpl }
}

describe('uploadDocument', () => {
  it('signs, PUTs a 20 MB file to Storage with no session token, then confirms', async () => {
    const { sent, fetchImpl } = recordingFetch()

    const doc = await uploadDocument(
      { file: fileOf(20 * MB), title: 'Gia phả', documentType: 'other' },
      { context, fetchImpl },
    )

    expect(doc.id).toBe(UPLOADED_ID)
    expect(sent.map((s) => s.target)).toEqual([
      'POST /documents/uploads',
      `PUT ${SIGNED.upload_url}`,
      'POST /documents',
    ])
    expect(JSON.parse(sent[0]!.body!)).toEqual({
      filename: 'gia-pha.jpg',
      content_type: 'image/jpeg',
      size_bytes: 20 * MB,
    })
    expect(JSON.parse(sent[2]!.body!)).toEqual({
      storage_path: SIGNED.storage_path,
      original_filename: 'gia-pha.jpg',
      title: 'Gia phả',
      document_type: 'other',
    })
    const put = sent[1]!
    expect(put.headers.get('authorization')).toBeNull()
    expect(put.headers.get('x-current-clan-id')).toBeNull()
    expect(put.headers.get('content-type')).toBe('image/jpeg')
  })

  it('refuses a file one byte over 50 MB before any request', async () => {
    const { sent, fetchImpl } = recordingFetch()

    await expect(
      uploadDocument(
        { file: fileOf(50 * MB + 1), title: 'x', documentType: 'other' },
        { context, fetchImpl },
      ),
    ).rejects.toBeInstanceOf(FileTooLargeError)
    expect(sent).toEqual([])
  })

  it('does not confirm a file Storage refused', async () => {
    const { sent, fetchImpl } = recordingFetch(415)

    await expect(
      uploadDocument(
        { file: fileOf(1024), title: 'x', documentType: 'other' },
        { context, fetchImpl },
      ),
    ).rejects.toBeInstanceOf(StorageUploadError)
    expect(sent.map((s) => s.target)).toEqual([
      'POST /documents/uploads',
      `PUT ${SIGNED.upload_url}`,
    ])
  })

  it('declares a type the browser does not know as octet-stream, so the API can name it', async () => {
    const { sent, fetchImpl } = recordingFetch()

    await uploadDocument(
      { file: fileOf(1024, ''), title: 'x', documentType: 'other' },
      { context, fetchImpl },
    )

    expect(JSON.parse(sent[0]!.body!)).toMatchObject({ content_type: 'application/octet-stream' })
  })
})

describe('listDocuments', () => {
  it('reads the cursor envelope into a page of domain summaries', async () => {
    const fetchImpl = vi.fn<FetchLike>(async () =>
      json({ data: [documentSummaryDto()], meta: { cursor: 'c2', has_more: true, limit: 20 } }),
    )

    const page = await listDocuments({}, { context, fetchImpl })

    expect(page).toEqual({
      items: [
        {
          id: documentSummaryDto().id,
          title: 'Gia phả chép tay 1925',
          documentType: 'certificate',
          mimeType: 'application/pdf',
          fileSizeBytes: 1024,
          isAvatar: false,
          createdAt: '2026-01-01T00:00:00Z',
        },
      ],
      cursor: 'c2',
      hasMore: true,
      limit: 20,
    })
  })
})
