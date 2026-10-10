// documentsApi.upload refuses a file over 4 MB before sending it (ADR-065, issue #250).
//
// The backend runs on Vercel Functions, which answer a body over 4.5 MB with their own
// 413, and that response never reaches the API's error envelope. So the outcome that
// matters is whether a request leaves the browser at all, not the constant. This test
// reads it from the transport: `api.post` is replaced, and each case asserts how many
// times it was called.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()

vi.mock('./axios', () => ({ default: { post: (...args: unknown[]) => post(...args) } }))

const { documentsApi } = await import('./documents')

const MB = 1024 * 1024
const meta = { title: 'Gia phả', document_type: 'photo' } as const

function fileOf(bytes: number): File {
  return new File([new Uint8Array(bytes)], 'gia-pha.jpg', { type: 'image/jpeg' })
}

describe('documentsApi.upload size cap', () => {
  beforeEach(() => {
    post.mockReset()
    post.mockResolvedValue({ data: { data: { id: 'doc-1' } } })
  })

  it('refuses a file one byte over 4 MB, names 4 MB, and sends nothing', async () => {
    await expect(documentsApi.upload(fileOf(4 * MB + 1), meta)).rejects.toThrow(
      'File size exceeds the 4 MB limit',
    )
    expect(post).not.toHaveBeenCalled()
  })

  it('refuses a file Vercel would answer with its own 413, and sends nothing', async () => {
    await expect(documentsApi.upload(fileOf(5 * MB), meta)).rejects.toThrow(/4 MB/)
    expect(post).not.toHaveBeenCalled()
  })

  it('sends a file of exactly 4 MB', async () => {
    await expect(documentsApi.upload(fileOf(4 * MB), meta)).resolves.toEqual({ id: 'doc-1' })
    expect(post).toHaveBeenCalledTimes(1)
    const [path, body] = post.mock.calls[0] as [string, FormData]
    expect(path).toBe('/documents')
    expect((body.get('file') as File).size).toBe(4 * MB)
  })
})
