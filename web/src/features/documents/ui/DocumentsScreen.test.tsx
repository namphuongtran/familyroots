import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClanRole } from '@/domain/capability/capability'
import { useSession } from '@/features/auth'
import type { components } from '@/generated/api-types'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, pageEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../messages/vi.json'
import zhMessages from '../../../../messages/zh.json'
import {
  CLAN_ID,
  documentResponseDto,
  documentSummaryDto,
  EXISTING_ID,
  signedUploadDto,
  UPLOADED_ID,
} from '../model/document-fixtures'
import { DocumentsScreen } from './DocumentsScreen'

/**
 * #313's readings, through the real session (`GET /auth/me`, `GET /me/clans`) and the real
 * request context, against MSW handlers that build the contract's envelopes. The API's documents
 * are one mutable list: the confirm handler adds to it and the delete handler removes from it, so
 * "the gallery shows the new document" is read off a refetch, not off the mutation's answer.
 *
 * Negative control for the oversized case (2026-11-21): with `MAX_UPLOAD_MB` raised to 60 in
 * `domain/document/document.ts`, above the backend's 50, the 51 MB case fails: no message, the
 * file is staged.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const vi_ = viMessages.documents
const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const SIGNED = signedUploadDto()
const MB = 1024 * 1024
const EXISTING_TITLE = documentSummaryDto().title
const NEW_TITLE = 'Ảnh nhà thờ họ'

type Summary = components['schemas']['DocumentSummary']

let stored: Summary[]
let sent: string[]

function profile(): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: CLAN_ID,
    clan_name: 'Nguyễn Phúc',
    role: null,
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
}

function serveAs(role: ClanRole) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile()))),
    http.get(`${API}/me/clans`, () =>
      HttpResponse.json(
        envelope<components['schemas']['UserClanMembership'][]>([
          { clan_id: CLAN_ID, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role },
        ]),
      ),
    ),
    http.get(`${API}/documents`, () => HttpResponse.json(pageEnvelope([...stored]))),
    http.get(`${API}/documents/:id`, ({ params }) =>
      HttpResponse.json(envelope(documentResponseDto({ id: String(params.id) }))),
    ),
    http.post(`${API}/documents/uploads`, () => HttpResponse.json(envelope(SIGNED))),
    http.put(SIGNED.upload_url.split('?')[0]!, () => new HttpResponse(null, { status: 200 })),
    http.post(`${API}/documents`, async ({ request }) => {
      const body = (await request.json()) as components['schemas']['DocumentCreateRequest']
      const created = documentResponseDto({
        id: UPLOADED_ID,
        title: body.title,
        document_type: body.document_type,
        mime_type: 'image/jpeg',
      })
      stored.unshift(documentSummaryDto({ id: UPLOADED_ID, title: body.title }))
      return HttpResponse.json(envelope(created), { status: 201 })
    }),
    http.delete(`${API}/documents/:id`, ({ params }) => {
      stored = stored.filter((d) => d.id !== params.id)
      return HttpResponse.json(envelope({ message: 'Document deleted', id: String(params.id) }))
    }),
  )
}

function ActiveRole() {
  return <p data-testid="active-role">{useSession().activeClan?.role ?? 'none'}</p>
}

async function renderAs(role: ClanRole) {
  serveAs(role)
  const view = renderWithProviders(
    <>
      <ActiveRole />
      <DocumentsScreen />
    </>,
    { messages },
  )
  await waitFor(() => expect(screen.getByTestId('active-role')).toHaveTextContent(role))
  await screen.findByText(EXISTING_TITLE)
  return view
}

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('no file input rendered')
  return input
}

function fileOf(name: string, bytes: number, type = 'image/jpeg'): File {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: bytes })
  return file
}

/** The document writes that left: everything but the session and the list/detail reads. */
function writes(): string[] {
  return sent.filter((s) => !s.startsWith('GET '))
}

function onRequest({ request }: { request: Request }) {
  const url = new URL(request.url)
  sent.push(
    `${request.method} ${url.origin === new URL(SIGNED.upload_url).origin ? 'storage' : url.pathname}`,
  )
}

beforeEach(() => {
  stored = [documentSummaryDto()]
  sent = []
  server.events.on('request:start', onRequest)
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN_ID)
})

afterEach(() => {
  server.events.removeListener('request:start', onRequest)
  clearClanCookie()
})

describe('upload', () => {
  it('signs, PUTs to Storage, confirms, and the gallery shows the new document', async () => {
    const user = userEvent.setup()
    const { container } = await renderAs('editor')

    await user.upload(fileInput(container), fileOf('nha-tho.jpg', 2 * MB))
    const title = screen.getByLabelText(expected(vi_.title))
    expect(title).toHaveValue('nha-tho')
    await user.clear(title)
    await user.type(title, NEW_TITLE)
    await user.click(screen.getByRole('button', { name: expected(vi_.upload) }))

    expect(await screen.findByText(NEW_TITLE)).toBeInTheDocument()
    expect(screen.getByText(EXISTING_TITLE)).toBeInTheDocument()
    expect(writes()).toEqual([
      'POST /api/v1/documents/uploads',
      'PUT storage',
      'POST /api/v1/documents',
    ])
    // The panel is ready for the next file.
    expect(screen.queryByLabelText(expected(vi_.title))).toBeNull()
  })

  it('refuses a 51 MB file with the 50 MB message before any request', async () => {
    const { container } = await renderAs('editor')

    fireEvent.change(fileInput(container), {
      target: { files: [fileOf('gia-pha.pdf', 51 * MB, 'application/pdf')] },
    })

    expect(
      screen.getByText(expected(vi_.file_too_large).replace('{max}', '50')),
    ).toBeInTheDocument()
    expect(screen.queryByText('gia-pha.pdf')).toBeNull()
    expect(screen.queryByRole('button', { name: expected(vi_.upload) })).toBeNull()
    expect(writes()).toEqual([])
  })

  it('stages a file of exactly 50 MB with no message', async () => {
    const { container } = await renderAs('editor')

    fireEvent.change(fileInput(container), {
      target: { files: [fileOf('gia-pha.pdf', 50 * MB, 'application/pdf')] },
    })

    expect(screen.getByText('gia-pha.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('says so when Storage refuses the file, and confirms nothing', async () => {
    const user = userEvent.setup()
    const { container } = await renderAs('editor')
    server.use(
      http.put(SIGNED.upload_url.split('?')[0]!, () => new HttpResponse(null, { status: 415 })),
    )

    await user.upload(fileInput(container), fileOf('nha-tho.jpg', 1024))
    await user.click(screen.getByRole('button', { name: expected(vi_.upload) }))

    expect(await screen.findByText(expected(vi_.upload_failed))).toBeInTheDocument()
    expect(writes()).toEqual(['POST /api/v1/documents/uploads', 'PUT storage'])
  })
})

describe("visibility: rbac.md's upload and delete line", () => {
  const deleteName = vi_.delete_document.replace('{title}', EXISTING_TITLE)

  it('an admin sees upload and the delete control', async () => {
    await renderAs('admin')

    expect(screen.getByText(expected(vi_.drop_hint))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: deleteName })).toBeInTheDocument()
  })

  it('an editor sees upload and no delete control', async () => {
    await renderAs('editor')

    expect(screen.getByText(expected(vi_.drop_hint))).toBeInTheDocument()
    expect(screen.queryByText(expected(vi_.no_upload_permission))).toBeNull()
    expect(screen.queryByRole('button', { name: deleteName })).toBeNull()
  })

  it('a viewer sees neither', async () => {
    await renderAs('viewer')

    expect(screen.getByText(expected(vi_.no_upload_permission))).toBeInTheDocument()
    expect(screen.queryByText(vi_.drop_hint)).toBeNull()
    expect(screen.queryByRole('button', { name: deleteName })).toBeNull()
  })

  it('a viewer is refused in Chinese under zh', async () => {
    serveAs('viewer')
    renderWithProviders(
      <>
        <ActiveRole />
        <DocumentsScreen />
      </>,
      { locale: 'zh', messages: zhMessages as unknown as AbstractIntlMessages },
    )
    await waitFor(() => expect(screen.getByTestId('active-role')).toHaveTextContent('viewer'))

    expect(
      screen.getByText(expected(zhMessages.documents.no_upload_permission)),
    ).toBeInTheDocument()
  })
})

describe('soft delete', () => {
  it('an admin deletes after confirming, and the document leaves the gallery', async () => {
    const user = userEvent.setup()
    await renderAs('admin')

    await user.click(
      screen.getByRole('button', { name: vi_.delete_document.replace('{title}', EXISTING_TITLE) }),
    )
    expect(writes()).toEqual([])
    await user.click(
      screen.getByRole('button', { name: vi_.confirm_delete.replace('{title}', EXISTING_TITLE) }),
    )

    await waitFor(() => expect(screen.queryByText(EXISTING_TITLE)).toBeNull())
    expect(writes()).toEqual([`DELETE /api/v1/documents/${EXISTING_ID}`])
    expect(await screen.findByText(expected(vi_.no_documents))).toBeInTheDocument()
  })
})

describe('open', () => {
  it('reads the document for its signed URL at the moment it is opened', async () => {
    const user = userEvent.setup()
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    await renderAs('viewer')
    const card = screen.getByText(EXISTING_TITLE).closest('li')!

    await user.click(within(card).getByRole('button', { name: expected(vi_.open) }))

    await waitFor(() =>
      expect(open).toHaveBeenCalledWith(
        documentResponseDto().presigned_url,
        '_blank',
        'noopener,noreferrer',
      ),
    )
    expect(sent).toContain(`GET /api/v1/documents/${EXISTING_ID}`)
    open.mockRestore()
  })
})
