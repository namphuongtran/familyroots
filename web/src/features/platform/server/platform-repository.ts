/**
 * The `platform` repository: fetch (`../api/platform-api`) → parse (`../model/platform-dto`) → map
 * to `@/domain/platform/platform`.
 */

import type { PlatformClanSummary, PlatformMetrics } from '@/domain/platform/platform'
import { unwrapData, unwrapPage, type Page } from '@/shared/http/envelope'
import * as api from '../api/platform-api'
import type { ListPlatformClansQuery, PlatformApiCallOptions } from '../api/platform-api'
import {
  clanSummaryDtoSchema,
  platformMetricsDtoSchema,
  toPlatformClanSummary,
  toPlatformMetrics,
} from '../model/platform-dto'

export type { ListPlatformClansQuery, PlatformApiCallOptions }

/** `GET /platform/clans`, one page. */
export async function listPlatformClans(
  query: ListPlatformClansQuery,
  options: PlatformApiCallOptions,
): Promise<Page<PlatformClanSummary>> {
  return unwrapPage(await api.listPlatformClans(query, options), (raw) =>
    toPlatformClanSummary(clanSummaryDtoSchema.parse(raw)),
  )
}

/** `GET /platform/metrics`. */
export async function getPlatformMetrics(
  options: PlatformApiCallOptions,
): Promise<PlatformMetrics> {
  return unwrapData(await api.getPlatformMetrics(options), (raw) =>
    toPlatformMetrics(platformMetricsDtoSchema.parse(raw)),
  )
}
