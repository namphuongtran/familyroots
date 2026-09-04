import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { REDACTED } from './redact'
import { WebVitalsReporter } from './web-vitals'

/**
 * the invitation page. `WebVitalsReporter` is mounted on every locale route
 * (`app/[locale]/layout.tsx:40`) and is the app's own log as well as its only
 * analytics call. It reported `window.location.pathname` verbatim, and on
 * `/{locale}/invitations/{token}` that pathname is a bearer credential
 * (`docs/contracts/rest-invitations-api.md:74`).
 *
 * These cases drive the real component and read what it actually wrote to the
 * console, rather than asserting that `redactInvitationToken` appears in the
 * source. `useReportWebVitals` is replaced with a capture so a metric can be
 * delivered on demand — jsdom reports no real Web Vitals.
 */

const TOKEN = 'Zx-9Qa_bC3dEfGhIjKlMnOpQrStUvWxYz0123456789'

const { reported } = vi.hoisted(() => ({ reported: { callback: null as unknown } }))

vi.mock('next/web-vitals', () => ({
  useReportWebVitals: (callback: unknown) => {
    reported.callback = callback
  },
}))

function deliverMetric(): void {
  const callback = reported.callback as (metric: {
    name: string
    value: number
    rating: string
  }) => void
  callback({ name: 'LCP', value: 1234.5, rating: 'good' })
}

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState({}, '', '/')
})

describe('WebVitalsReporter', () => {
  it('logs the invitation route with the token removed', () => {
    window.history.replaceState({}, '', `/vi/invitations/${TOKEN}`)
    // The control for this whole file: if the browser location did not actually
    // carry the token, every assertion below would pass for the wrong reason.
    expect(window.location.pathname).toContain(TOKEN)
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    render(<WebVitalsReporter />)

    deliverMetric()

    const record = info.mock.calls[0][1] as { route?: string }
    expect(record.route).toBe(`/vi/invitations/${REDACTED}`)
    expect(JSON.stringify(info.mock.calls)).not.toContain(TOKEN)
  })

  it('still reports the metric itself, so the fix did not silence the telemetry', () => {
    window.history.replaceState({}, '', `/vi/invitations/${TOKEN}`)
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    render(<WebVitalsReporter />)

    deliverMetric()

    expect(info.mock.calls[0][0]).toBe('[web-vitals]')
    expect(info.mock.calls[0][1]).toMatchObject({ metric: 'LCP', value: 1235, rating: 'good' })
  })

  it('leaves an ordinary route exactly as it was', () => {
    window.history.replaceState({}, '', '/vi/login')
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    render(<WebVitalsReporter />)

    deliverMetric()

    expect((info.mock.calls[0][1] as { route?: string }).route).toBe('/vi/login')
  })
})
