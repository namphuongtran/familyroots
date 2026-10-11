// documentsApi.upload sends a document's bytes straight to Storage (ADR-068, issue #256).
//
// Three requests, in order: the API signs a staged path, the browser PUTs the file to the
// signed URL, and the API confirms it. The outcome that matters is where the bytes go, not a
// constant. So each case reads the transport: `api.post` and the global `fetch` are replaced,
// and the case asserts which requests left, in what order, and what each one carried. No
// request to the API may carry the file, because Vercel refuses an API body over 4.5 MB with
// its own 413, which never reaches the API's error envelope (ADR-065).
//
// Negative control, 2026-10-11: with the PUT sent through `api.post('/documents', file)`
// instead of `fetch`, "sends a 20 MB file to Storage, never to the API" fails.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
const fetchMock = vi.fn()

vi.mock('./axios', () => ({ default: { post: (...args: unknown[]) => post(...args) } }))

const { documentsApi } = await import('./documents')

const MB = 1024 * 1024
const meta = { title: 'Gia phả', document_type: 'photo' } as const
const SIGNED = {
  storage_path: 'clans/c1/uploads/0b9a3c1e-0000-4000-8000-000000000001.jpg',
  upload_url: 'https://storage.example/object/upload/sign/family-roots-files/x?token=t1',
  token: 't1',
  expires_at: '2026-10-11T12:00:00Z',
}

function fileOf(bytes: number, type = 'image/jpeg'): File {
  return new File([new Uint8Array(bytes)], 'gia-pha.jpg', { type })
}

/** Every request that left, in order, as `[target, body]`. */
function requests(): [string, unknown][] {
  const sent: { order: number; target: string; body: unknown }[] = [
    ...post.mock.calls.map((call, i) => ({
      order: post.mock.invocationCallOrder[i],
      target: `api ${call[0] as string}`,
      body: call[1],
    })),
    ...fetchMock.mock.calls.map((call, i) => ({
      order: fetchMock.mock.invocationCallOrder[i],
      target: `${(call[1] as RequestInit).method} ${call[0] as string}`,
      body: (call[1] as RequestInit).body,
    })),
  ]
  return sent.sort((a, b) => a.order - b.order).map((r) => [r.target, r.body])
}

beforeEach(() => {
  post.mockReset()
  fetchMock.mockReset()
  post.mockImplementation((path: string) =>
    Promise.resolve(
      path === '/documents/uploads'
        ? { data: { data: SIGNED } }
        : { data: { data: { id: 'doc-1' } } },
    ),
  )
  fetchMock.mockResolvedValue(new Response(null, { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('documentsApi.upload', () => {
  it('sends a 20 MB file to Storage, never to the API', async () => {
    const file = fileOf(20 * MB)

    await expect(documentsApi.upload(file, meta)).resolves.toEqual({ id: 'doc-1' })

    expect(requests()).toEqual([
      [
        'api /documents/uploads',
        { filename: 'gia-pha.jpg', content_type: 'image/jpeg', size_bytes: 20 * MB },
      ],
      [`PUT ${SIGNED.upload_url}`, file],
      [
        'api /documents',
        {
          storage_path: SIGNED.storage_path,
          original_filename: 'gia-pha.jpg',
          title: 'Gia phả',
          document_type: 'photo',
        },
      ],
    ])
    // The PUT carries no session token: the signed URL is its only authorization.
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.headers).toEqual({ 'Content-Type': 'image/jpeg' })
  })

  it('refuses a file one byte over 50 MB, names 50 MB, and sends nothing', async () => {
    await expect(documentsApi.upload(fileOf(50 * MB + 1), meta)).rejects.toThrow(
      'File size exceeds the 50 MB limit',
    )
    expect(requests()).toEqual([])
  })

  it('does not confirm a file Storage refused', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 415 }))

    await expect(documentsApi.upload(fileOf(1024), meta)).rejects.toThrow(/415/)

    expect(requests().map(([target]) => target)).toEqual([
      'api /documents/uploads',
      `PUT ${SIGNED.upload_url}`,
    ])
  })

  it('declares a type the browser does not know as octet-stream, so the API can name it', async () => {
    await documentsApi.upload(fileOf(1024, ''), meta)

    expect(post.mock.calls[0][1]).toMatchObject({ content_type: 'application/octet-stream' })
  })
})
