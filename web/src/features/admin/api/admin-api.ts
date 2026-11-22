/**
 * Transport for docs/contracts/rest-clans-api.md: the clan's own profile, its counts, its account
 * lists, and the admin's actions on them. Calls `apiFetch` and nothing else. No React, no parsing:
 * every function returns the raw body and `../server/admin-repository.ts` parses and maps it.
 *
 * Every route here is clan-scoped by `X-Current-Clan-Id`, which `apiFetch` sends from
 * `context.clanId`.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'
import type { components } from '@/generated/api-types'

export type AdminApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

export type ClanUpdateRequest = components['schemas']['ClanUpdateRequest']

export interface ListClanUsersQuery {
  /** Opaque — pass back exactly what a previous page's `meta.cursor` returned. */
  cursor?: string | null
  limit?: number
}

/** `GET /clans/me`, with `?include=stats` when `withStats` is set. */
export function getOwnClan(withStats: boolean, options: AdminApiCallOptions): Promise<unknown> {
  return apiFetch('/clans/me', {
    ...options,
    method: 'GET',
    query: { include: withStats ? 'stats' : undefined },
  })
}

/** `PATCH /clans/me` — admin. A partial update; the 200 body is the stored row after the write. */
export function updateOwnClan(
  body: ClanUpdateRequest,
  options: AdminApiCallOptions,
): Promise<unknown> {
  return apiFetch('/clans/me', { ...options, method: 'PATCH', body })
}

/** `GET /clans/me/users` — viewer. Approved accounts, cursor-paginated. */
export function listClanUsers(
  query: ListClanUsersQuery,
  options: AdminApiCallOptions,
): Promise<unknown> {
  return apiFetch('/clans/me/users', {
    ...options,
    method: 'GET',
    query: { cursor: query.cursor, limit: query.limit },
  })
}

/** `GET /clans/me/users/pending` — admin. Pending join requests, cursor-paginated, with `email`. */
export function listPendingClanUsers(
  query: ListClanUsersQuery,
  options: AdminApiCallOptions,
): Promise<unknown> {
  return apiFetch('/clans/me/users/pending', {
    ...options,
    method: 'GET',
    query: { cursor: query.cursor, limit: query.limit },
  })
}

/** `POST /clans/me/users/{user_id}/approve` — admin. */
export function approveClanUser(userId: string, options: AdminApiCallOptions): Promise<unknown> {
  return apiFetch(`/clans/me/users/${encodeURIComponent(userId)}/approve`, {
    ...options,
    method: 'POST',
  })
}

/** `POST /clans/me/users/{user_id}/reject` — admin. */
export function rejectClanUser(userId: string, options: AdminApiCallOptions): Promise<unknown> {
  return apiFetch(`/clans/me/users/${encodeURIComponent(userId)}/reject`, {
    ...options,
    method: 'POST',
  })
}

/** `PATCH /clans/me/users/{user_id}/role` — admin. `role` is a query parameter, not a body field. */
export function changeClanUserRole(
  userId: string,
  role: string,
  options: AdminApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/clans/me/users/${encodeURIComponent(userId)}/role`, {
    ...options,
    method: 'PATCH',
    query: { role },
  })
}
