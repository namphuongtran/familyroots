import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import enMessages from '../../../../messages/en.json'
import { PlatformMetricsScreen } from './PlatformMetricsScreen'

/** #314: each tile reads its own field of `GET /platform/metrics`, not a neighbour's. */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
})

describe('the platform metrics tiles', () => {
  it('show each total under its own label', async () => {
    server.use(
      http.get(`${API}/platform/metrics`, () =>
        HttpResponse.json(
          envelope({
            total_clans: 11,
            active_clans: 9,
            suspended_clans: 2,
            total_members: 4321,
            total_users: 87,
          }),
        ),
      ),
    )
    renderWithProviders(<PlatformMetricsScreen />, { locale: 'en', messages: enMessages })

    const p = enMessages.platform
    for (const [label, value] of [
      [p.total_clans, '11'],
      [p.active_clans, '9'],
      [p.suspended_clans, '2'],
      [p.total_members, '4321'],
      [p.total_users, '87'],
    ] as const) {
      await waitFor(() =>
        expect(screen.getByText(expected(label)).parentElement).toHaveTextContent(value),
      )
    }
  })
})
