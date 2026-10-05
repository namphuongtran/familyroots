import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClanRole } from '@/domain/capability/capability'
import { useSession } from '@/features/auth'
import type { components } from '@/generated/api-types'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, pageEnvelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../messages/vi.json'
import { DocumentGallery } from './DocumentGallery'
import { DocumentUpload } from './DocumentUpload'

/**
 * #185: the two legacy documents components read `uploadDocument` and `deleteDocument` from
 * `useCapabilities()` in `@/features/auth`, through the real session hook.
 * `docs/architecture/rbac.md:101-102` draws the line: upload is admin and editor, delete is admin
 * only. The documents slice itself is
 * not migrated here; the gallery still lists through the legacy axios client, which MSW answers
 * with the real list envelope.
 *
 * The delete control is an icon-only button with no accessible name, so `deleteControls()` finds
 * it by its trash icon, the thing a sighted user sees. Naming it is the documents slice's work.
 *
 * Each case waits for the session to settle on the role and for the document to be listed before
 * reading. Every capability is false while the session loads, so a viewer case read early would
 * pass whatever role came back.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
/** The legacy axios client's own base URL (`lib/api/axios.ts`). */
const LEGACY_API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'
const DOCUMENT_TITLE = 'Gia phả chép tay 1925'

const UPLOAD_HINT = 'Kéo thả tệp vào đây'
const NO_UPLOAD = 'You do not have permission to upload documents.'

function profile(): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: CLAN_A,
    clan_name: 'Nguyễn Phúc',
    role: null,
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
}

function document(): components['schemas']['DocumentSummary'] {
  return {
    id: 'dddddddd-0000-4000-8000-000000000001',
    title: DOCUMENT_TITLE,
    document_type: 'certificate',
    mime_type: 'application/pdf',
    file_size_bytes: 1024,
    is_avatar: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function serveAs(role: ClanRole) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile()))),
    http.get(`${API}/me/clans`, () =>
      HttpResponse.json(
        envelope<components['schemas']['UserClanMembership'][]>([
          { clan_id: CLAN_A, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role },
        ]),
      ),
    ),
    http.get(`${LEGACY_API}/documents`, () => HttpResponse.json(pageEnvelope([document()]))),
  )
}

function ActiveRole() {
  return <p data-testid="active-role">{useSession().activeClan?.role ?? 'none'}</p>
}

async function renderDocumentsAs(role: ClanRole) {
  serveAs(role)
  renderWithProviders(
    <>
      <ActiveRole />
      <DocumentUpload />
      <DocumentGallery />
    </>,
    { messages },
  )
  await waitFor(() => expect(screen.getByTestId('active-role')).toHaveTextContent(role))
  await screen.findByText(DOCUMENT_TITLE)
}

function deleteControls(): HTMLElement[] {
  return screen
    .queryAllByRole('button')
    .filter((button) => button.querySelector('svg[class*="lucide-trash"]') !== null)
}

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN_A)
})

afterEach(() => {
  clearClanCookie()
})

describe("the documents components draw rbac.md's upload and delete line", () => {
  it('an admin sees upload and the delete control', async () => {
    await renderDocumentsAs('admin')

    expect(screen.getByText(UPLOAD_HINT)).toBeInTheDocument()
    expect(deleteControls()).toHaveLength(1)
  })

  it('an editor sees upload and no delete control', async () => {
    await renderDocumentsAs('editor')

    expect(screen.getByText(UPLOAD_HINT)).toBeInTheDocument()
    expect(screen.queryByText(NO_UPLOAD)).not.toBeInTheDocument()
    expect(deleteControls()).toHaveLength(0)
  })

  it('a viewer sees neither', async () => {
    await renderDocumentsAs('viewer')

    expect(screen.getByText(NO_UPLOAD)).toBeInTheDocument()
    expect(screen.queryByText(UPLOAD_HINT)).not.toBeInTheDocument()
    expect(deleteControls()).toHaveLength(0)
  })
})
