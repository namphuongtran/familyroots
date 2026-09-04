/**
 * Transport for the `persons` resource. Calls `apiFetch` and nothing else —
 * no React, no parsing, no mapping. `api-layer-has-no-react`
 * (`.dependency-cruiser.cjs`) enforces the first half; the second half is
 * this file's own discipline, because the rule cannot see it: every function
 * here returns the raw enveloped JSON (`Promise<unknown>`), same as
 * `apiFetch` itself. Validating it against `../model/person-dto.ts` and
 * mapping it into `@/domain/person` is the repository's job, not
 * this layer's.
 *
 * Deliberately covers only the core `persons` surface —
 * `docs/contracts/rest-persons-api.md` — and not the relationship-shaped
 * sub-resources nested under `/persons/{id}/*` (`marriages`, `parent-child`,
 * `documents`, `events`, `timeline`, `claim`): those return payloads that
 * belong to the relationships, documents, events, and claims slices, not to
 * this one.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'
import type { components } from '@/generated/api-types'

type PersonCreateRequest = components['schemas']['PersonCreateRequest']
type PersonUpdateRequest = components['schemas']['PersonUpdateRequest']
type PersonBatchGetRequest = components['schemas']['PersonBatchGetRequest']

/**
 * Every call needs a `RequestContext`; the rest of `ApiFetchOptions` (the
 * fetch injection seam, the abort signal, the single-flight refresh hook) is
 * the caller's to pass through, same as `apiFetch` itself takes it.
 */
export type PersonsApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

export interface ListPersonsQuery {
  /** Opaque — pass back exactly what a previous page's `meta.cursor` returned. */
  cursor?: string | null
  limit?: number
  generation?: number | null
  gender?: string | null
  profile?: 'summary' | 'detail' | 'full'
  include?: string | null
  fields?: string | null
}

export interface GetPersonQuery {
  include?: string | null
  fields?: string | null
  profile?: 'summary' | 'detail' | 'full'
}

export interface SearchPersonsQuery {
  q: string
  limit?: number
}

/**
 * `apiFetch`'s `query` option is a plain `Record<string, ...>` — an index
 * signature the specific, literal-typed query interfaces below intentionally
 * do not carry, so this is the one narrow, explicit cast between them rather
 * than loosening those interfaces to fit.
 */
function asQuery<T extends object>(query: T): ApiFetchOptions['query'] {
  return query as ApiFetchOptions['query']
}

/** `GET /persons` — cursor-paginated list. Returns `PageEnvelope[PersonResponse]`. */
export function listPersons(
  query: ListPersonsQuery,
  options: PersonsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/persons', { ...options, method: 'GET', query: asQuery(query) })
}

/** `GET /persons/search` — a plain array under `data`, no `meta`. */
export function searchPersons(
  query: SearchPersonsQuery,
  options: PersonsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/persons/search', { ...options, method: 'GET', query: asQuery(query) })
}

/** `GET /persons/{id}` — a single resource under `data`. */
export function getPerson(
  id: string,
  query: GetPersonQuery,
  options: PersonsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/persons/${id}`, { ...options, method: 'GET', query: asQuery(query) })
}

/**
 * `POST /persons/batch` — always 200 even on partial failure. `data` holds
 * the resolved persons; unresolved ids are reported under `meta.errors`,
 * never mixed into `data`.
 */
export function batchGetPersons(
  body: PersonBatchGetRequest,
  options: PersonsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/persons/batch', { ...options, method: 'POST', body })
}

/** `POST /persons` — a single resource under `data`, 201. */
export function createPerson(
  body: PersonCreateRequest,
  options: PersonsApiCallOptions,
): Promise<unknown> {
  return apiFetch('/persons', { ...options, method: 'POST', body })
}

/**
 * `PATCH /persons/{id}` — `body.expected_version` is required (ADR-017); a
 * mismatch is a `409 stale_write`, not something this layer resolves.
 */
export function updatePerson(
  id: string,
  body: PersonUpdateRequest,
  options: PersonsApiCallOptions,
): Promise<unknown> {
  return apiFetch(`/persons/${id}`, { ...options, method: 'PATCH', body })
}

/** `DELETE /persons/{id}` — soft delete; returns a `MessageData` envelope. */
export function deletePerson(id: string, options: PersonsApiCallOptions): Promise<unknown> {
  return apiFetch(`/persons/${id}`, { ...options, method: 'DELETE' })
}

/** `POST /persons/{id}/restore` — returns a `MessageData` envelope. */
export function restorePerson(id: string, options: PersonsApiCallOptions): Promise<unknown> {
  return apiFetch(`/persons/${id}/restore`, { ...options, method: 'POST' })
}
