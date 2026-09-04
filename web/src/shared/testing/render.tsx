import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl'
import type { ReactElement, ReactNode } from 'react'

/**
 * A QueryClient per render, with retries off: a retrying query turns an
 * assertion failure into a timeout and hides the real error.
 *
 * The return type is inferred on purpose. Annotating it
 * `RenderResult & { queryClient: QueryClient }` does not compile: with a
 * `wrapper` option TypeScript resolves `render` to a narrower result than the
 * default `RenderResult`, and reports all 48 query helpers as missing.
 *
 * `messages`/`locale` are new for the pending-approval screen: the first component tests to render
 * a screen that calls `useTranslations` (the blocked-state screens) need a
 * real `NextIntlClientProvider` in the tree, or the hook throws. Pass the
 * real locale file (`web/messages/<locale>.json`), never a hand-written
 * subset — the same "no invented shape" rule `shared/testing/msw.ts` applies
 * to response bodies applies to translations: a test that supplies its own
 * copy cannot catch a missing key in the real file. Omitting `messages`
 * (empty object) is harmless for the existing tests in this directory, none
 * of which call `useTranslations`.
 */
export function renderWithProviders(
  ui: ReactElement,
  intl: { locale?: string; messages?: AbstractIntlMessages } = {},
) {
  const { locale = 'vi', messages = {} } = intl
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={messages}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </NextIntlClientProvider>
    )
  }

  return { ...render(ui, { wrapper: Wrapper }), queryClient }
}
