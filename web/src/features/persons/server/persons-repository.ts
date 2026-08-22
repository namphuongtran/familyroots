/**
 * The `persons` repository: fetch (`../api/persons-api`) → parse (the zod
 * schemas in `../model/person-dto`) → map to domain (`@/domain/person/person`).
 * `web/CLAUDE.md`'s Architecture section names these as three separate
 * steps; this file is where they run in one place, and the only place —
 * every function here returns a domain type, never a DTO and never the raw
 * enveloped body S-029's `api/` layer hands back.
 *
 * Every function takes a `RequestContext` inside its `PersonsApiCallOptions`,
 * passed in by the caller rather than read from a global. That is what lets
 * the *same* function run inside a Server Component (`getServerRequestContext`)
 * and in the browser (`getClientRequestContext`) — see
 * `persons-repository.two-runtimes.test.tsx`.
 */

import type { components } from '@/generated/api-types'
import type {
  Person,
  PersonActionResult,
  PersonBatchResult,
  PersonSearchHit,
  PersonWriteResult,
} from '@/domain/person/person'
import { ApiError, INVALID_CURSOR_CODE, MalformedResponseError } from '@/shared/http/errors'
import { unwrapData, unwrapPage, type Page } from '@/shared/http/envelope'
import * as api from '../api/persons-api'
import type {
  GetPersonQuery,
  ListPersonsQuery,
  PersonsApiCallOptions,
  SearchPersonsQuery,
} from '../api/persons-api'
import {
  batchErrorDtoSchema,
  messageDataDtoSchema,
  personResponseDtoSchema,
  personSearchResultDtoSchema,
  toPerson,
  toPersonActionResult,
  toPersonBatchError,
  toPersonSearchHit,
  type BatchErrorDto,
} from '../model/person-dto'

/**
 * Not exported from `../api/persons-api` (that file keeps them as private
 * aliases too, for the same reason: the generated `components` type is the
 * one source of truth, and a re-export would just be a second name for it).
 */
type PersonCreateRequest = components['schemas']['PersonCreateRequest']
type PersonUpdateRequest = components['schemas']['PersonUpdateRequest']
type PersonBatchGetRequest = components['schemas']['PersonBatchGetRequest']

export type { PersonsApiCallOptions, ListPersonsQuery, GetPersonQuery, SearchPersonsQuery }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parsePerson(raw: unknown): Person {
  return toPerson(personResponseDtoSchema.parse(raw))
}

/** `GET /persons/{id}`. */
export async function getPerson(
  id: string,
  query: GetPersonQuery,
  options: PersonsApiCallOptions,
): Promise<Person> {
  const body = await api.getPerson(id, query, options)
  return unwrapData(body, parsePerson)
}

/**
 * `GET /persons` — a `Page<Person>`.
 *
 * On `400 invalid_cursor` this drops the cursor and refetches page one
 * itself, per the cursor rule in `web/CLAUDE.md` and the root `CLAUDE.md`:
 * cursors are opaque, so the only correct response to a rejected one is to
 * stop sending it, never to repair it. Doing the retry here rather than in
 * `hooks/` keeps the behaviour testable without React, and means every
 * caller of this repository function gets it for free — a screen cannot
 * forget to handle it because there is nothing left for a screen to handle.
 */
export async function listPersons(
  query: ListPersonsQuery,
  options: PersonsApiCallOptions,
): Promise<Page<Person>> {
  try {
    const body = await api.listPersons(query, options)
    return unwrapPage(body, parsePerson)
  } catch (error) {
    if (error instanceof ApiError && error.code === INVALID_CURSOR_CODE && query.cursor != null) {
      const body = await api.listPersons({ ...query, cursor: null }, options)
      return unwrapPage(body, parsePerson)
    }
    throw error
  }
}

/** `GET /persons/search` — a plain array under `data`, no `meta`. */
export async function searchPersons(
  query: SearchPersonsQuery,
  options: PersonsApiCallOptions,
): Promise<PersonSearchHit[]> {
  const body = await api.searchPersons(query, options)
  return unwrapData(body, (raw) => {
    if (!Array.isArray(raw)) {
      throw new MalformedResponseError('search response data is not an array')
    }
    return raw.map((item) => toPersonSearchHit(personSearchResultDtoSchema.parse(item)))
  })
}

/**
 * `POST /persons/batch` — always 200 even on partial failure. `data` holds
 * the resolved persons; `meta.errors` holds the ids that did not resolve.
 * `unwrapPage` does not fit this shape (there is no `has_more`/`limit`
 * cursor triplet, `meta.errors` instead), so this is its own small envelope
 * reader rather than a forced reuse of `unwrapPage`.
 */
export async function batchGetPersons(
  body: PersonBatchGetRequest,
  options: PersonsApiCallOptions,
): Promise<PersonBatchResult> {
  const raw = await api.batchGetPersons(body, options)
  if (!isRecord(raw) || !Array.isArray(raw.data)) {
    throw new MalformedResponseError(
      'batch response is not a {"data": [...], "meta": {"errors": [...]}} envelope',
    )
  }
  const meta = raw.meta
  const rawErrors: unknown[] = isRecord(meta) && Array.isArray(meta.errors) ? meta.errors : []
  const errors: BatchErrorDto[] = rawErrors.map((item) => batchErrorDtoSchema.parse(item))
  return {
    items: raw.data.map(parsePerson),
    errors: errors.map(toPersonBatchError),
  }
}

/**
 * Reads `meta.warning` off a write response's envelope (spec §7.7a: "a
 * successful write ... the save succeeds, and a `warning` toast appears
 * afterwards"). Deliberately not `unwrapPage` or a new case inside
 * `unwrapData` — `unwrapData`'s whole contract is "hand back `data`, see
 * nothing else," the same reason `batchGetPersons` above reads its own
 * `meta` rather than forcing itself through a shared reader. A raw body with
 * no `meta`, a non-string `warning`, or `meta` shaped some other way all map
 * to `null` rather than throwing — an absent or malformed warning is not a
 * contract violation the way a missing `data` key is.
 */
function readWriteWarning(raw: unknown): string | null {
  if (!isRecord(raw) || !isRecord(raw.meta)) return null
  const { warning } = raw.meta
  return typeof warning === 'string' ? warning : null
}

/**
 * `POST /persons`. `body` is typed straight from the generated
 * `PersonCreateRequest`, not validated with zod — see this feature's own
 * `../api/persons-api.ts` doc comment and `web/CLAUDE.md`'s "Write DTOs skip
 * zod on purpose": the caller constructs it and TypeScript already checks
 * the shape at the call site, so a schema here would validate a value this
 * module never received untrusted.
 */
export async function createPerson(
  body: PersonCreateRequest,
  options: PersonsApiCallOptions,
): Promise<PersonWriteResult> {
  const raw = await api.createPerson(body, options)
  return { person: unwrapData(raw, parsePerson), warning: readWriteWarning(raw) }
}

/**
 * `PATCH /persons/{id}`. `body.expected_version` is the caller's job
 * (ADR-017) — a mismatch surfaces as the `stale_write` `ApiError` this
 * function throws unchanged, for `ui/PersonForm.tsx` to catch.
 */
export async function updatePerson(
  id: string,
  body: PersonUpdateRequest,
  options: PersonsApiCallOptions,
): Promise<PersonWriteResult> {
  const raw = await api.updatePerson(id, body, options)
  return { person: unwrapData(raw, parsePerson), warning: readWriteWarning(raw) }
}

/** `DELETE /persons/{id}` — soft delete; returns a `MessageData` envelope. */
export async function deletePerson(
  id: string,
  options: PersonsApiCallOptions,
): Promise<PersonActionResult> {
  const raw = await api.deletePerson(id, options)
  return unwrapData(raw, (item) => toPersonActionResult(messageDataDtoSchema.parse(item)))
}

/** `POST /persons/{id}/restore` — returns a `MessageData` envelope. */
export async function restorePerson(
  id: string,
  options: PersonsApiCallOptions,
): Promise<PersonActionResult> {
  const raw = await api.restorePerson(id, options)
  return unwrapData(raw, (item) => toPersonActionResult(messageDataDtoSchema.parse(item)))
}
