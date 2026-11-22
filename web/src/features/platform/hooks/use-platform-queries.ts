'use client'

/** TanStack Query wrappers over `../server/platform-repository`. */

import { useQuery } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import { getPlatformMetrics, listPlatformClans } from '../server/platform-repository'
import { platformKeys } from '../server/query-keys'

export interface PlatformQueryOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

/**
 * The contract's largest page. The clan list reads one page, as the legacy hook it replaces did
 * (that one read the default 20); a "load more" is not built yet.
 */
export const PLATFORM_CLANS_PAGE_LIMIT = 100

/** `GET /platform/clans`, first page, as a plain list. */
export function usePlatformClans(options: PlatformQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: platformKeys.clans(),
    queryFn: async ({ signal }) =>
      (
        await listPlatformClans(
          { limit: PLATFORM_CLANS_PAGE_LIMIT },
          { context, refreshAuth, signal },
        )
      ).items,
    enabled,
  })
}

/** `GET /platform/metrics`. */
export function usePlatformMetrics(options: PlatformQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useQuery({
    queryKey: platformKeys.metrics(),
    queryFn: ({ signal }) => getPlatformMetrics({ context, refreshAuth, signal }),
    enabled,
  })
}
