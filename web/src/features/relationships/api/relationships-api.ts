/**
 * Transport for the `relationships` resource. Calls `apiFetch` and nothing
 * else — no React, no parsing, no mapping. `api-layer-has-no-react`
 * (`.dependency-cruiser.cjs`) enforces the first half; the second half is
 * this file's own discipline. Every function returns `Promise<unknown>`, the
 * raw enveloped body. The repository is the one place DTO parsing and
 * mapping into `@/domain/relationship` happen.
 *
 * Covers docs/contracts/rest-relationships-api.md, plus the two person-centric
 * read endpoints that live under `/persons/{person_id}/{marriages,parent-child}`
 * because the issue's End state names them as the aside's data source. The
 * sub-resource routes are listed here, not on the persons slice, because they
 * return `MarriageResponse` / `ParentChildResponse` payloads this slice owns.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'
import type { components } from '@/generated/api-types'

type MarriageCreateRequest = components['schemas']['MarriageCreateRequest']
type MarriageUpdateRequest = components['schemas']['MarriageUpdateRequest']
type ParentChildCreateRequest = components['schemas']['ParentChildCreateRequest']
type ParentChildUpdateRequest = components['schemas']['ParentChildUpdateRequest']

/**
 * Every call needs a `RequestContext`; the rest of `ApiFetchOptions` (the
 * fetch injection seam, the abort signal, the single-flight refresh hook) is
 * the caller's to pass through, same as `apiFetch` itself takes it.
 */
export type RelationshipsApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

/** `GET /persons/{person_id}/marriages` — a plain array under `data`, no meta. */
export function listPersonMarriages(
  personId: string,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/persons/${personId}/marriages`, { ...options, method: 'GET' })
}

/** `GET /persons/{person_id}/parent-child` — a plain array under `data`, no meta. */
export function listPersonParentChild(
  personId: string,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/persons/${personId}/parent-child`, { ...options, method: 'GET' })
}

/** `GET /relationships/marriages/{id}` — a single resource under `data`. */
export function getMarriage(id: string, options: RelationshipsApiCallOptions): Promise<unknown> {
  return apiFetch(`/relationships/marriages/${id}`, { ...options, method: 'GET' })
}

/** `POST /relationships/marriages` — a single resource under `data`, 201. */
export function createMarriage(
  body: MarriageCreateRequest,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/relationships/marriages', { ...options, method: 'POST', body })
}

/** `PATCH /relationships/marriages/{id}` — `body.expected_version` is required (ADR-017). */
export function updateMarriage(
  id: string,
  body: MarriageUpdateRequest,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/relationships/marriages/${id}`, { ...options, method: 'PATCH', body })
}

/** `DELETE /relationships/marriages/{id}` — soft-delete, returns `MessageData`. */
export function deleteMarriage(id: string, options: RelationshipsApiCallOptions): Promise<unknown> {
  return apiFetch(`/relationships/marriages/${id}`, { ...options, method: 'DELETE' })
}

/** `GET /relationships/parent-child/{id}` — a single resource under `data`. */
export function getParentChild(id: string, options: RelationshipsApiCallOptions): Promise<unknown> {
  return apiFetch(`/relationships/parent-child/${id}`, { ...options, method: 'GET' })
}

/** `POST /relationships/parent-child` — single resource + optional `meta.warning`. */
export function createParentChild(
  body: ParentChildCreateRequest,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/relationships/parent-child', { ...options, method: 'POST', body })
}

/** `PATCH /relationships/parent-child/{id}` — `body.expected_version` is required (ADR-017). */
export function updateParentChild(
  id: string,
  body: ParentChildUpdateRequest,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/relationships/parent-child/${id}`, { ...options, method: 'PATCH', body })
}

/** `DELETE /relationships/parent-child/{id}` — soft-delete, returns `MessageData`. */
export function deleteParentChild(
  id: string,
  options: RelationshipsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/relationships/parent-child/${id}`, { ...options, method: 'DELETE' })
}
