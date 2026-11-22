import { Component, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { renderWithProviders } from '@/shared/testing/render'
import viMessages from '../../../messages/vi.json'
import LocaleError from '@/app/[locale]/error'
import GlobalError from '@/app/global-error'
import MembersError from '@/app/[locale]/(dashboard)/members/error'
import MemberDetailError from '@/app/[locale]/(dashboard)/members/[id]/error'

const captureException = vi.fn()
vi.mock('@sentry/nextjs', () => ({ captureException: (e: unknown) => captureException(e) }))

/**
 * #366. Mirrors what Next does: a child throws on render, a boundary catches it and renders the
 * route's `error.tsx` with the caught error. The assertion is the outcome, one `captureException`
 * call with that error. Negative control: with the effect removed from `useReportError`, every
 * case fails with zero calls.
 */
const boom = new Error('render failed')

function Thrower(): ReactNode {
  throw boom
}

type Fallback = (error: Error) => ReactNode
class Boundary extends Component<{ fallback: Fallback; children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {}
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children
  }
}

const noop = () => {}
const cases: [string, Fallback][] = [
  ['the locale boundary', (e) => <LocaleError error={e} unstable_retry={noop} />],
  ['the members boundary', (e) => <MembersError error={e} reset={noop} />],
  ['the member detail boundary', (e) => <MemberDetailError error={e} reset={noop} />],
]

describe('error boundaries report to Sentry', () => {
  beforeEach(() => {
    captureException.mockClear()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it.each(cases)('%s reports the caught error once', (_name, fallback) => {
    renderWithProviders(
      <Boundary fallback={fallback}>
        <Thrower />
      </Boundary>,
      { locale: 'vi', messages: viMessages },
    )

    expect(captureException).toHaveBeenCalledTimes(1)
    expect(captureException).toHaveBeenCalledWith(boom)
  })

  it('the global boundary reports the caught error once', () => {
    // `<html>` inside a container div warns, which is irrelevant to the reading
    render(
      <Boundary fallback={(e) => <GlobalError error={e} unstable_retry={noop} />}>
        <Thrower />
      </Boundary>,
    )

    expect(captureException).toHaveBeenCalledTimes(1)
    expect(captureException).toHaveBeenCalledWith(boom)
  })
})
