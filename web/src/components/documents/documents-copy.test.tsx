import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { getCapabilities, type ClanRole } from '@/domain/capability/capability'
import { useCapabilities } from '@/features/auth'
import type { components } from '@/generated/api-types'
import { pageEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import viMessages from '../../../messages/vi.json'
import zhMessages from '../../../messages/zh.json'
import { DocumentGallery } from './DocumentGallery'
import { DocumentUpload } from './DocumentUpload'

/**
 * #194: three English literals in the documents components. The gallery's open button said
 * `Open`, then `Opening...` while it fetched the signed URL, and the upload panel told a viewer
 * `You do not have permission to upload documents.`, all in English for every locale.
 *
 * Who may upload is `documents-capabilities.test.tsx`'s question, through the real session. Here
 * the role is an input, so `useCapabilities` returns the real `getCapabilities` table for it.
 *
 * Negative control, 2026-10-06, with the keys in all four locale files and the components still
 * holding the literals: the open case failed with `Unable to find role="button" and name "Mở"`,
 * with `Open` in the printed DOM, and the viewer case with
 * `Unable to find an element with the text: 您无权上传文档。`. With only `Opening...` put back,
 * the open case failed on its second read: `Unable to find role="button" and name "Đang mở..."`.
 */

vi.mock('@/features/auth', () => ({ useCapabilities: vi.fn() }))

/** The legacy axios client's own base URL (`lib/api/axios.ts`). */
const LEGACY_API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'
const DOCUMENT_ID = 'dddddddd-0000-4000-8000-000000000001'

function documentSummary(): components['schemas']['DocumentSummary'] {
  return {
    id: DOCUMENT_ID,
    title: 'Gia phả chép tay 1925',
    document_type: 'certificate',
    mime_type: 'application/pdf',
    file_size_bytes: 1024,
    is_avatar: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function actAs(role: ClanRole) {
  vi.mocked(useCapabilities).mockReturnValue(getCapabilities(role))
}

describe('the gallery open button, under the vi locale', () => {
  it('names the button in Vietnamese, and says so in Vietnamese while it opens', async () => {
    actAs('viewer')
    server.use(
      http.get(`${LEGACY_API}/documents`, () =>
        HttpResponse.json(pageEnvelope([documentSummary()])),
      ),
      // Held open, so the button stays in its opening state for the read.
      http.get(`${LEGACY_API}/documents/${DOCUMENT_ID}`, async () => {
        await delay('infinite')
        return HttpResponse.json({})
      }),
    )
    renderWithProviders(<DocumentGallery />, { locale: 'vi', messages: viMessages })

    const open = await screen.findByRole('button', { name: expected(viMessages.documents.open) })
    await userEvent.click(open)

    expect(
      await screen.findByRole('button', { name: expected(viMessages.documents.opening) }),
    ).toBeDisabled()
  })
})

describe('the upload panel for a viewer', () => {
  it('refuses in Chinese under the zh locale', () => {
    actAs('viewer')
    renderWithProviders(<DocumentUpload />, { locale: 'zh', messages: zhMessages })

    expect(
      screen.getByText(expected(zhMessages.documents.no_upload_permission)),
    ).toBeInTheDocument()
  })
})
