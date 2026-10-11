import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSession } from '@/features/auth'
import type { components } from '@/generated/api-types'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../messages/vi.json'
import { DocumentUpload } from './DocumentUpload'

/**
 * #250, then #256: the screen refuses a file the transport would refuse. `lib/api/documents.ts`
 * throws past its limit before sending, and nothing catches that rejection in `handleSubmit`.
 * While this screen allowed 20 MB and the transport 4, a 4-20 MB file was accepted here and then
 * failed with nothing shown. Since #256 the file goes straight to Storage (ADR-068) and the limit
 * is 50 MB. The case reads what a person gets: the size message and no file staged, or the file
 * staged and no message.
 *
 * Negative control, 2026-10-10: with `MAX_MB = 20` put back, the over-limit case failed, the
 * 5 MB file was staged and no message appeared. Re-run 2026-10-11 at 50 MB: with `MAX_MB = 60`,
 * the 51 MB case fails the same way.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'
const MB = 1024 * 1024
const TOO_LARGE = expected(viMessages.documents.file_too_large).replace('{max}', '50')

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

function ActiveRole() {
  return <p data-testid="active-role">{useSession().activeClan?.role ?? 'none'}</p>
}

async function renderAsEditor() {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile()))),
    http.get(`${API}/me/clans`, () =>
      HttpResponse.json(
        envelope<components['schemas']['UserClanMembership'][]>([
          { clan_id: CLAN_A, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role: 'editor' },
        ]),
      ),
    ),
  )
  const { container } = renderWithProviders(
    <>
      <ActiveRole />
      <DocumentUpload />
    </>,
    { messages },
  )
  await waitFor(() => expect(screen.getByTestId('active-role')).toHaveTextContent('editor'))
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('no file input rendered')
  return input
}

function fileOf(name: string, bytes: number): File {
  const file = new File(['x'], name, { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: bytes })
  return file
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

describe('DocumentUpload refuses what the transport would refuse', () => {
  it('a 51 MB file shows the 50 MB message and is not staged', async () => {
    const input = await renderAsEditor()

    fireEvent.change(input, { target: { files: [fileOf('gia-pha.pdf', 51 * MB)] } })

    expect(screen.getByText(TOO_LARGE)).toBeInTheDocument()
    expect(screen.queryByText('gia-pha.pdf')).not.toBeInTheDocument()
  })

  it('a 20 MB file, refused before #256, is staged with no message', async () => {
    const input = await renderAsEditor()

    fireEvent.change(input, { target: { files: [fileOf('gia-pha.pdf', 20 * MB)] } })

    expect(screen.getByText('gia-pha.pdf')).toBeInTheDocument()
    expect(screen.queryByText(TOO_LARGE)).not.toBeInTheDocument()
  })

  it('a file of exactly 50 MB is staged with no message', async () => {
    const input = await renderAsEditor()

    fireEvent.change(input, { target: { files: [fileOf('gia-pha.pdf', 50 * MB)] } })

    expect(screen.getByText('gia-pha.pdf')).toBeInTheDocument()
    expect(screen.queryByText(TOO_LARGE)).not.toBeInTheDocument()
  })
})
