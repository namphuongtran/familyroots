import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { captureException } from '@sentry/nextjs'
import { renderWithProviders } from '@/shared/testing/render'
import LocaleError from './[locale]/error'
import MembersError from './[locale]/(dashboard)/members/error'
import MemberDetailError from './[locale]/(dashboard)/members/[id]/error'
import GlobalError from './global-error'
import viMessages from '../../messages/vi.json'

vi.mock('@sentry/nextjs', () => ({ captureException: vi.fn() }))

/**
 * #366: a client-side render error reached no one. Each boundary is given the error Next hands
 * it and must report that error to Sentry once, however often it re-renders.
 */
const boom = new Error('boom')
const noop = () => {}

const BOUNDARIES: [string, () => React.ReactElement][] = [
  ['locale', () => <LocaleError error={boom} unstable_retry={noop} />],
  ['members', () => <MembersError error={boom} reset={noop} />],
  ['member detail', () => <MemberDetailError error={boom} reset={noop} />],
  ['global', () => <GlobalError error={boom} unstable_retry={noop} />],
]

describe('error boundaries report to Sentry', () => {
  beforeEach(() => vi.mocked(captureException).mockClear())

  it.each(BOUNDARIES)('%s reports its error once', (_name, make) => {
    const { rerender } = renderWithProviders(make(), { locale: 'vi', messages: viMessages })
    rerender(make())
    expect(captureException).toHaveBeenCalledTimes(1)
    expect(captureException).toHaveBeenCalledWith(boom)
  })

  it('global shows a bilingual message without the locale layout', () => {
    renderWithProviders(<GlobalError error={boom} unstable_retry={noop} />)
    expect(screen.getByText(/Đã xảy ra lỗi/)).toBeInTheDocument()
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument()
  })
})
