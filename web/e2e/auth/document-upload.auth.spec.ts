import { createHash } from 'node:crypto'
import { expect, test, type Request } from '@playwright/test'
import { authStackInputs, SEEDED_USERS } from './fixtures'
import { browserAccessToken } from './session-cookie'

/**
 * #256, ADR-068: a 20 MB document goes from the browser straight to Supabase Storage.
 *
 * On Vercel a request body over 4.5 MB never reaches the API (ADR-065), which is why uploads
 * were capped at 4 MB while the bytes went through `POST /documents`. Now the API signs a staged
 * path, the browser PUTs the file to the signed URL, and the API confirms what Storage holds.
 * This walk runs the real screen against the real local stack, so it reads what no unit test can:
 * that the browser may PUT cross-origin to Storage, and that the bytes Storage keeps are the
 * file's.
 *
 * Three readings. Every request to the API is small, and the one PUT to Storage carries the
 * file. The confirm call answers 201 with the stored size. The returned `presigned_url` serves
 * the same 20 MB, byte for byte, by SHA-256.
 *
 * It spends two `GET /auth/me` from the rate-limit bucket, the server guard's and the browser's,
 * like any one load of a `(dashboard)` screen. The document it makes is soft-deleted at the end.
 *
 * Read 2026-10-11 against the local stack: 4 passed, the setups included. Negative control the
 * same day: with the transport PUTting the file less its last byte, the walk failed on the stored
 * size, `Expected: 20971520`, `Received: 20971519`. A failed run leaves its document live.
 */

const MB = 1024 * 1024
/** Generous for a JSON body, and three orders of magnitude under the file. */
const API_BODY_LIMIT = 16 * 1024

/** 20 MB that compress to nothing useful, and that a re-run reproduces exactly. */
function twentyMegabytes(): Buffer {
  const bytes = Buffer.alloc(20 * MB)
  let state = 0x2545f491
  for (let i = 0; i < bytes.length; i += 1) {
    state ^= state << 13
    state ^= state >>> 17
    state ^= state << 5
    bytes[i] = state & 0xff
  }
  return bytes
}

const sha256 = (bytes: Buffer): string => createHash('sha256').update(bytes).digest('hex')

test.describe('document upload, as an admin', () => {
  test.use({ storageState: SEEDED_USERS.admin.storageState })

  test('a 20 MB file goes to Storage, not through the API, and Storage keeps its bytes', async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000)
    const { apiOrigin } = authStackInputs()
    const file = twentyMegabytes()
    const name = `gia-pha-${Date.now()}.png`

    const apiWrites: Request[] = []
    const storagePuts: Request[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.origin === apiOrigin && request.method() !== 'GET') apiWrites.push(request)
      if (request.method() === 'PUT' && url.pathname.includes('/storage/v1/object/upload/sign/')) {
        storagePuts.push(request)
      }
    })

    await page.goto('/vi/documents')
    await expect(page).toHaveURL(/\/vi\/documents$/)

    await page.locator('input[type="file"]').setInputFiles({
      name,
      mimeType: 'image/png',
      buffer: file,
    })
    const confirmed = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/documents',
      { timeout: 90_000 },
    )
    await page.getByRole('button', { name: 'Tải lên' }).click()
    const response = await confirmed

    expect(response.status()).toBe(201)
    const document = (await response.json()).data as {
      id: string
      storage_path: string
      file_size_bytes: number
      mime_type: string
      presigned_url: string
    }
    expect(document.file_size_bytes).toBe(20 * MB)
    expect(document.mime_type).toBe('image/png')
    expect(document.storage_path).toMatch(/^clans\/[0-9a-f-]{36}\/documents\/[0-9a-f-]{36}\.png$/)

    // The API saw two small JSON bodies, sign and confirm, and never the file.
    expect(apiWrites.map((r) => new URL(r.url()).pathname)).toEqual([
      '/api/v1/documents/uploads',
      '/api/v1/documents',
    ])
    for (const request of apiWrites) {
      expect(request.postDataBuffer()?.length ?? 0).toBeLessThan(API_BODY_LIMIT)
    }
    expect(storagePuts).toHaveLength(1)
    expect((await storagePuts[0].response())?.status()).toBe(200)

    // What Storage keeps is the file.
    const download = await page.request.get(document.presigned_url)
    expect(download.status()).toBe(200)
    const stored = await download.body()
    expect(stored.length).toBe(file.length)
    expect(sha256(stored)).toBe(sha256(file))

    // Leave the seeded clan as it was: soft-delete the document (ADR-019).
    const token = await browserAccessToken(context)
    const clanId = (await context.cookies()).find((c) => c.name === 'current_clan_id')?.value
    const removed = await page.request.delete(`${apiOrigin}/api/v1/documents/${document.id}`, {
      headers: { Authorization: `Bearer ${token}`, 'X-Current-Clan-Id': clanId ?? '' },
    })
    expect(removed.status()).toBe(200)
  })
})
