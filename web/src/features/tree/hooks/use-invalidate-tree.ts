'use client'

import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { treeKeys } from '../server/query-keys'

/**
 * Invalidates every tree entry of a clan. `tree` imports `persons` and `relationships`, so they
 * cannot import this; the caller (a page or `TreeScreen`) passes it down as `onSaved` / `onChanged`.
 */
export function useInvalidateTree(clanId: string | null): () => void {
  const queryClient = useQueryClient()
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: treeKeys.all(clanId) })
  }, [queryClient, clanId])
}
