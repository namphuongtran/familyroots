/**
 * Transport for the read half of docs/contracts/rest-platform-admin-api.md. Calls `apiFetch` and
 * nothing else; `../server/platform-repository.ts` parses and maps.
 *
 * Not clan-scoped: every route is gated by the super-admin check on `user_profiles.platform_role`,
 * so the screens read their context with `clanScoped: false` and send no `X-Current-Clan-Id`.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'

export type PlatformApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

export interface ListPlatformClansQuery {
  /** Opaque — pass back exactly what a previous page's `meta.cursor` returned. */
  cursor?: string | null
  limit?: number
}

/** `GET /platform/clans` — cursor-paginated. */
export function listPlatformClans(
  query: ListPlatformClansQuery,
  options: PlatformApiCallOptions,
): Promise<unknown> {
  return apiFetch('/platform/clans', {
    ...options,
    method: 'GET',
    query: { cursor: query.cursor, limit: query.limit },
  })
}

/** `GET /platform/metrics` — platform-wide totals. */
export function getPlatformMetrics(options: PlatformApiCallOptions): Promise<unknown> {
  return apiFetch('/platform/metrics', { ...options, method: 'GET' })
}
