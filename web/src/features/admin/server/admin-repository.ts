/**
 * The `admin` repository: fetch (`../api/admin-api`) → parse (`../model/clan-dto`) → map to
 * `@/domain/clan/clan-profile`. Returns domain values only.
 */

import type {
  ClanProfile,
  ClanProfileUpdate,
  ClanStats,
  ClanUsers,
} from '@/domain/clan/clan-profile'
import type { ClanRole } from '@/domain/capability/capability'
import { unwrapData, unwrapPage } from '@/shared/http/envelope'
import * as api from '../api/admin-api'
import type { AdminApiCallOptions } from '../api/admin-api'
import {
  clanResponseDtoSchema,
  clanUserSummaryDtoSchema,
  clanWithStatsDtoSchema,
  pendingClanUserSummaryDtoSchema,
  toClanProfile,
  toClanStats,
  toClanUpdateRequest,
  toClanUser,
  toPendingClanUser,
} from '../model/clan-dto'

export type { AdminApiCallOptions }

/**
 * The contract's largest page (`limit` 1–100). The admin screens read one page of each list, as
 * the legacy hook they replace did (it read the default 20). A clan with more than 100 accounts in
 * one list needs a "load more", which no screen has yet.
 */
export const CLAN_USERS_PAGE_LIMIT = 100

const parseProfile = (raw: unknown) => toClanProfile(clanResponseDtoSchema.parse(raw))

/** `GET /clans/me`. */
export async function getClanProfile(options: AdminApiCallOptions): Promise<ClanProfile> {
  return unwrapData(await api.getOwnClan(false, options), parseProfile)
}

/** `GET /clans/me?include=stats`: the counts only. */
export async function getClanStats(options: AdminApiCallOptions): Promise<ClanStats> {
  return unwrapData(await api.getOwnClan(true, options), (raw) =>
    toClanStats(clanWithStatsDtoSchema.parse(raw).stats),
  )
}

/** `PATCH /clans/me`. Resolves the stored row after the write. */
export async function updateClanProfile(
  update: ClanProfileUpdate,
  options: AdminApiCallOptions,
): Promise<ClanProfile> {
  return unwrapData(await api.updateOwnClan(toClanUpdateRequest(update), options), parseProfile)
}

/** `GET /clans/me/users` and `GET /clans/me/users/pending`, in parallel, one page each. */
export async function listClanUsers(options: AdminApiCallOptions): Promise<ClanUsers> {
  const query = { limit: CLAN_USERS_PAGE_LIMIT }
  const [approved, pending] = await Promise.all([
    api.listClanUsers(query, options),
    api.listPendingClanUsers(query, options),
  ])
  return {
    approved: unwrapPage(approved, (raw) => toClanUser(clanUserSummaryDtoSchema.parse(raw))).items,
    pending: unwrapPage(pending, (raw) =>
      toPendingClanUser(pendingClanUserSummaryDtoSchema.parse(raw)),
    ).items,
  }
}

export async function approveClanUser(userId: string, options: AdminApiCallOptions): Promise<void> {
  await api.approveClanUser(userId, options)
}

export async function rejectClanUser(userId: string, options: AdminApiCallOptions): Promise<void> {
  await api.rejectClanUser(userId, options)
}

export async function changeClanUserRole(
  userId: string,
  role: ClanRole,
  options: AdminApiCallOptions,
): Promise<void> {
  await api.changeClanUserRole(userId, role, options)
}
