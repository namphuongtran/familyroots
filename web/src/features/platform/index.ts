/**
 * Public surface of the `platform` slice: the super-admin's clan list and metrics
 * (docs/contracts/rest-platform-admin-api.md). Other code imports this slice through this file
 * only; the raw `api/` transport is not re-exported.
 */

export type { PlatformClanSummary, PlatformMetrics } from '@/domain/platform/platform'

export type { ListPlatformClansQuery, PlatformApiCallOptions } from './server/platform-repository'
export { getPlatformMetrics, listPlatformClans } from './server/platform-repository'
export { platformKeys } from './server/query-keys'

export type { PlatformQueryOptions } from './hooks/use-platform-queries'
export {
  PLATFORM_CLANS_PAGE_LIMIT,
  usePlatformClans,
  usePlatformMetrics,
} from './hooks/use-platform-queries'

export { PlatformClansScreen } from './ui/PlatformClansScreen'
export { PlatformMetricsScreen } from './ui/PlatformMetricsScreen'
