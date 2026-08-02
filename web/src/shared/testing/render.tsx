import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'

/**
 * A QueryClient per render, with retries off: a retrying query turns an
 * assertion failure into a timeout and hides the real error.
 *
 * The return type is inferred on purpose. Annotating it
 * `RenderResult & { queryClient: QueryClient }` does not compile: with a
 * `wrapper` option TypeScript resolves `render` to a narrower result than the
 * default `RenderResult`, and reports all 48 query helpers as missing.
 */
export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }

  return { ...render(ui, { wrapper: Wrapper }), queryClient }
}
