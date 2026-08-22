'use client'

import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth.store'

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        retry: 1,
      },
    },
  })
}

let browserQueryClient: QueryClient | undefined = undefined

function getQueryClient() {
  if (typeof window === 'undefined') {
    return makeQueryClient()
  }
  if (!browserQueryClient) browserQueryClient = makeQueryClient()
  return browserQueryClient
}

export function Providers({ children }: { children: React.ReactNode }) {
  const queryClient = getQueryClient()

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
