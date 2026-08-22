/**
 * The pure genealogical person (docs/contracts/rest-persons-api.md).
 *
 * Plain TypeScript, same as the rest of `src/domain/`: no React, no zod, no
 * fetch. `features/persons/model/person-dto.ts` is the only module that knows
 * how to turn a wire `PersonResponse` into one of these — this file never
 * parses anything, it only names the shape the mapper produces.
 */

import type { HistoricalDate } from '@/domain/date/historical-date'

/**
 * The backend constrains `gender` to this pattern
 * (`backend/app/schemas/person.py:37`, `:95`); the generated OpenAPI type
 * widens it to a bare `string` because the schema encodes the constraint as a
 * regex, not an enum. `features/persons/model/person-dto.ts` is what narrows
 * it back down, and does so by parsing — an unrecognised value fails loudly
 * there rather than reaching this type as a lie.
 */
export type Gender = 'male' | 'female' | 'unknown'

/**
 * Mirrors `components.schemas.PersonResponse` in the generated OpenAPI types,
 * field for field, but camelCased and with every `HistoricalDate` already
 * mapped through `@/domain/date/historical-date`.
 *
 * `avatarUrl` is read-only on the wire (ADR-036) — nothing in this feature
 * ever constructs or writes one; it only ever renders what the API returned.
 */
export interface Person {
  readonly id: string
  readonly createdByClanId: string | null
  readonly fullName: string
  readonly birthName: string | null
  readonly courtesyName: string | null
  readonly posthumousName: string | null
  readonly aliasName: string | null
  readonly gender: Gender
  readonly birthDate: HistoricalDate | null
  readonly deathDate: HistoricalDate | null
  readonly birthPlace: string | null
  readonly deathPlace: string | null
  readonly burialPlace: string | null
  readonly tombLocation: string | null
  readonly residencePlace: string | null
  readonly religion: string | null
  readonly nationality: string
  readonly occupation: string | null
  readonly educationLevel: string | null
  readonly titleRank: string | null
  readonly phone: string | null
  readonly email: string | null
  readonly biography: string | null
  readonly avatarUrl: string | null
  readonly notes: string | null
  readonly isDeleted: boolean
  readonly createdBy: string
  readonly updatedBy: string | null
  readonly createdAt: string
  readonly updatedAt: string
  /** Optimistic-concurrency token (ADR-017). Round-trip it as `expected_version`. */
  readonly version: number
}

/**
 * Mirrors `components.schemas.PersonSearchResult` — the lean projection
 * `GET /persons/search` returns. Unlike {@link Person}, `birthDate` is
 * required on the wire (search always includes it) rather than optional.
 */
export interface PersonSearchHit {
  readonly id: string
  readonly fullName: string
  readonly gender: Gender
  readonly birthDate: HistoricalDate
  readonly avatarUrl: string | null
  readonly version: number
  readonly generation: number | null
  readonly membershipRole: string | null
  readonly isFounder: boolean
}

/**
 * Mirrors `components.schemas.MessageData` — the confirmation body
 * `DELETE /persons/{id}` and `POST /persons/{id}/restore` return. Not a
 * persistent record, just the outcome of an action.
 */
export interface PersonActionResult {
  readonly message: string
  readonly id: string | null
}

/**
 * The result of `POST /persons` or `PATCH /persons/{id}` (S-032). Spec
 * §7.7a: "`meta.warning` on a successful write ... the save succeeds, and a
 * `warning` toast appears afterwards." The envelope's `meta` is discarded by
 * `unwrapData` on every other read (nothing else has ever needed it), so the
 * write path is the one place a repository function reads past `data` on a
 * 2xx — `warning` is `null` on every response that carried no `meta.warning`
 * string, which is the common case.
 */
export interface PersonWriteResult {
  readonly person: Person
  readonly warning: string | null
}

/**
 * One row of `POST /persons/batch`'s `meta.errors` — a requested id that did
 * not resolve. Mirrors `components.schemas.BatchError`.
 */
export interface PersonBatchError {
  readonly id: string
  readonly code: string
}

/**
 * The outcome of `POST /persons/batch` (`components.schemas.PersonBatchEnvelope`):
 * the persons that resolved and the ids that did not, kept apart rather than
 * merged — `docs/contracts/rest-persons-api.md` is explicit that an
 * unresolved id is "never mixed into `data`".
 */
export interface PersonBatchResult {
  readonly items: readonly Person[]
  readonly errors: readonly PersonBatchError[]
}
