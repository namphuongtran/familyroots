/**
 * the auth-store split's two required proofs: switching clan changes what a query returns
 * without a page reload, and a reload preserves the selection. Both rest on
 * the same mechanism — `useCurrentClanId` (this file's `context.client.ts`)
 * reads the `current_clan_id` cookie reactively, so a TanStack Query
 * key built from it refetches on `writeClanCookie` without any component
 * unmounting, and a fresh mount (standing in for a real page reload, which
 * always re-reads the cookie rather than any client-side store) resolves the
 * same clan immediately because the cookie — not a store — is what persists.
 */
import { useQuery } from '@tanstack/react-query'
import { act, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { apiFetch } from './api-client'
import { CLAN_COOKIE } from './request-context'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'

// Deferred: `useCurrentClanId` is only imported inside the test bodies below
// (dynamic `await import`) so the negative-control instructions in the seed
// — replace the export, watch this file fail, restore it — do not require
// touching this file at all.
async function loadUseCurrentClanId() {
  const mod = await import('./context.client')
  return mod.useCurrentClanId
}

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

function setBrowserCookie(value: string | null) {
  // jsdom keeps existing cookies around between assignments, so clear the
  // slot before writing a new value rather than only ever appending — the
  // same trap `context.test.tsx` documents.
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
  if (value !== null) {
    document.cookie = `${CLAN_COOKIE}=${encodeURIComponent(value)}; path=/`
  }
}

function registerPingHandler() {
  server.use(
    http.get(`${API}/ping`, ({ request }) =>
      HttpResponse.json(envelope({ seenClanId: request.headers.get('x-current-clan-id') })),
    ),
  )
}

function ClanScopedPing({ useCurrentClanId }: { useCurrentClanId: () => string | null }) {
  const clanId = useCurrentClanId()
  const { data } = useQuery({
    queryKey: ['ping', clanId],
    queryFn: async () => {
      const body = (await apiFetch('/ping', {
        context: { locale: 'vi', clanId, accessToken: null },
      })) as { data: { seenClanId: string | null } }
      return body.data.seenClanId
    },
  })
  return <div data-testid="seen-clan">{data ?? 'loading'}</div>
}

const CLAN_A = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const CLAN_B = 'a1b2c3d4-1111-2222-3333-444455556666'

describe('switching the active clan', () => {
  afterEach(() => {
    setBrowserCookie(null)
  })

  it('changes what a running query returns, without unmounting anything', async () => {
    registerPingHandler()
    setBrowserCookie(CLAN_A)
    const useCurrentClanId = await loadUseCurrentClanId()

    renderWithProviders(<ClanScopedPing useCurrentClanId={useCurrentClanId} />)

    await waitFor(() => expect(screen.getByTestId('seen-clan')).toHaveTextContent(CLAN_A))

    const { writeClanCookie } = await import('./context.client')
    act(() => {
      writeClanCookie(CLAN_B)
    })

    // Same render tree throughout — no unmount, no `render()` call in
    // between — which is what "without a page reload" means here.
    await waitFor(() => expect(screen.getByTestId('seen-clan')).toHaveTextContent(CLAN_B))
  })

  it('a fresh mount resolves the previously selected clan, which is the cookie surviving a reload', async () => {
    registerPingHandler()
    // No writeClanCookie call in this test at all — the cookie is set the
    // way a real reload would find it: already sitting in the browser from
    // a previous page, with no store or React tree carried over.
    setBrowserCookie(CLAN_B)
    const useCurrentClanId = await loadUseCurrentClanId()

    renderWithProviders(<ClanScopedPing useCurrentClanId={useCurrentClanId} />)

    await waitFor(() => expect(screen.getByTestId('seen-clan')).toHaveTextContent(CLAN_B))
  })
})
