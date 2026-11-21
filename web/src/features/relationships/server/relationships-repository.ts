/**
 * The `relationships` repository: fetch (`../api/relationships-api`) → parse
 * (the zod schemas in `../model/*`) → map to domain (`@/domain/relationship`).
 * Every function here returns a domain type, never a DTO and never the raw
 * `Promise<unknown>` the transport layer hands back.
 *
 * Writes follow ADR-017: `createMarriage`/`createParentChild` return
 * `*WriteResult` so the optional `meta.warning` string (spec §7.7a and
 * docs/contracts/rest-relationships-api.md's `POST /parent-child` warning)
 * reaches the caller. `updateMarriage`/`updateParentChild` take a body
 * carrying `expected_version` — a mismatch surfaces as a `409 stale_write`
 * `ApiError` for the editor to catch. Delete bumps `version` but does not
 * require `expected_version`.
 *
 * The per-person reads intentionally do **not** fail on an empty array:
 * docs/contracts/rest-persons-api.md's edge-visibility rule says an edge is
 * hidden when the endpoint person is soft-deleted, and a person with no
 * live spouses or no live children is a routine case the aside must render
 * as a quiet empty state — not an error.
 */

import type { components } from '@/generated/api-types'
import type {
  Marriage,
  MarriageWriteResult,
  ParentChild,
  ParentChildWriteResult,
  RelationshipActionResult,
} from '@/domain/relationship/relationship'
import { MalformedResponseError } from '@/shared/http/errors'
import { unwrapData } from '@/shared/http/envelope'
import * as api from '../api/relationships-api'
import type { RelationshipsApiCallOptions } from '../api/relationships-api'
import { marriageResponseDtoSchema, toMarriage } from '../model/marriage-dto'
import { parentChildResponseDtoSchema, toParentChild } from '../model/parent-child-dto'
import { messageDataDtoSchema, toRelationshipActionResult } from '../model/message-data-dto'

type MarriageCreateRequest = components['schemas']['MarriageCreateRequest']
type MarriageUpdateRequest = components['schemas']['MarriageUpdateRequest']
type ParentChildCreateRequest = components['schemas']['ParentChildCreateRequest']
type ParentChildUpdateRequest = components['schemas']['ParentChildUpdateRequest']

export type { RelationshipsApiCallOptions }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseMarriage(raw: unknown): Marriage {
  return toMarriage(marriageResponseDtoSchema.parse(raw))
}

function parseParentChild(raw: unknown): ParentChild {
  return toParentChild(parentChildResponseDtoSchema.parse(raw))
}

/**
 * `unwrapData` over a plain-array `data`. Mirrors
 * `persons-repository.ts`'s `searchPersons` shape: `GET
 * /persons/{id}/{marriages,parent-child}` is not cursor-paginated, so it is
 * `{"data": [...]}` with no `meta`.
 */
function unwrapArray<T>(body: unknown, parseItem: (raw: unknown) => T): T[] {
  return unwrapData(body, (raw) => {
    if (!Array.isArray(raw)) {
      throw new MalformedResponseError('list response data is not an array')
    }
    return raw.map(parseItem)
  })
}

/**
 * Reads `meta.warning` off a write-response envelope. Same reader
 * `persons-repository.ts` uses for its own write paths (spec §7.7a). Absence
 * or malformation maps to null rather than throwing — an absent warning is
 * not a contract violation the way a missing `data` is.
 */
function readWriteWarning(raw: unknown): string | null {
  if (!isRecord(raw) || !isRecord(raw.meta)) return null
  const { warning } = raw.meta
  return typeof warning === 'string' ? warning : null
}

/** `GET /persons/{person_id}/marriages`. */
export async function listPersonMarriages(
  personId: string,
  options: RelationshipsApiCallOptions,
): Promise<Marriage[]> {
  const body = await api.listPersonMarriages(personId, options)
  return unwrapArray(body, parseMarriage)
}

/** `GET /persons/{person_id}/parent-child`. */
export async function listPersonParentChild(
  personId: string,
  options: RelationshipsApiCallOptions,
): Promise<ParentChild[]> {
  const body = await api.listPersonParentChild(personId, options)
  return unwrapArray(body, parseParentChild)
}

/** `GET /relationships/marriages/{id}`. */
export async function getMarriage(
  id: string,
  options: RelationshipsApiCallOptions,
): Promise<Marriage> {
  const body = await api.getMarriage(id, options)
  return unwrapData(body, parseMarriage)
}

/** `GET /relationships/parent-child/{id}`. */
export async function getParentChild(
  id: string,
  options: RelationshipsApiCallOptions,
): Promise<ParentChild> {
  const body = await api.getParentChild(id, options)
  return unwrapData(body, parseParentChild)
}

/** `POST /relationships/marriages`. */
export async function createMarriage(
  body: MarriageCreateRequest,
  options: RelationshipsApiCallOptions,
): Promise<MarriageWriteResult> {
  const raw = await api.createMarriage(body, options)
  return { marriage: unwrapData(raw, parseMarriage), warning: readWriteWarning(raw) }
}

/** `PATCH /relationships/marriages/{id}`. */
export async function updateMarriage(
  id: string,
  body: MarriageUpdateRequest,
  options: RelationshipsApiCallOptions,
): Promise<MarriageWriteResult> {
  const raw = await api.updateMarriage(id, body, options)
  return { marriage: unwrapData(raw, parseMarriage), warning: readWriteWarning(raw) }
}

/** `DELETE /relationships/marriages/{id}`. */
export async function deleteMarriage(
  id: string,
  options: RelationshipsApiCallOptions,
): Promise<RelationshipActionResult> {
  const raw = await api.deleteMarriage(id, options)
  return unwrapData(raw, (item) => toRelationshipActionResult(messageDataDtoSchema.parse(item)))
}

/** `POST /relationships/parent-child`. */
export async function createParentChild(
  body: ParentChildCreateRequest,
  options: RelationshipsApiCallOptions,
): Promise<ParentChildWriteResult> {
  const raw = await api.createParentChild(body, options)
  return { parentChild: unwrapData(raw, parseParentChild), warning: readWriteWarning(raw) }
}

/** `PATCH /relationships/parent-child/{id}`. */
export async function updateParentChild(
  id: string,
  body: ParentChildUpdateRequest,
  options: RelationshipsApiCallOptions,
): Promise<ParentChildWriteResult> {
  const raw = await api.updateParentChild(id, body, options)
  return { parentChild: unwrapData(raw, parseParentChild), warning: readWriteWarning(raw) }
}

/** `DELETE /relationships/parent-child/{id}`. */
export async function deleteParentChild(
  id: string,
  options: RelationshipsApiCallOptions,
): Promise<RelationshipActionResult> {
  const raw = await api.deleteParentChild(id, options)
  return unwrapData(raw, (item) => toRelationshipActionResult(messageDataDtoSchema.parse(item)))
}
