/**
 * The pure genealogical relationship types (docs/contracts/rest-relationships-api.md).
 *
 * Plain TypeScript, same as the rest of `src/domain/`: no React, no zod, no
 * fetch. `features/relationships/model/*` is the only place that knows how to
 * turn wire `MarriageResponse` and `ParentChildResponse` payloads into these;
 * this file only names the shape the mapper produces.
 *
 * The backend's `status` (marriage) and `relationship_type` (parent-child)
 * are constrained to a pattern in the generated OpenAPI type, so the schema
 * at the boundary narrows them back down to these unions. An unrecognised
 * value fails loudly at parse time rather than reaching the domain as a lie.
 */

import type { HistoricalDate } from '@/domain/date/historical-date'

export type MarriageStatus = 'married' | 'divorced' | 'widowed' | 'separated'

export type ParentChildType = 'biological' | 'adopted' | 'step' | 'foster'

/**
 * Mirrors `components.schemas.MarriageResponse` field for field, camelCased.
 * `version` is ADR-017's optimistic-concurrency token; round-trip it as
 * `expected_version` on `PATCH`/`DELETE`.
 */
export interface Marriage {
  readonly id: string
  readonly person1Id: string
  readonly person2Id: string
  readonly createdByClanId: string
  readonly status: MarriageStatus
  readonly marriageDate: HistoricalDate | null
  readonly divorceDate: HistoricalDate | null
  readonly marriagePlace: string | null
  readonly spouseOrder: number | null
  readonly notes: string | null
  readonly createdBy: string
  readonly updatedBy: string | null
  readonly isDeleted: boolean
  readonly deletedAt: string | null
  readonly deletedBy: string | null
  readonly createdAt: string
  readonly updatedAt: string
  readonly version: number
}

/** Mirrors `components.schemas.ParentChildResponse` field for field, camelCased. */
export interface ParentChild {
  readonly id: string
  readonly parentId: string
  readonly childId: string
  readonly createdByClanId: string
  readonly relationshipType: ParentChildType
  readonly birthOrder: number | null
  readonly notes: string | null
  readonly createdBy: string
  readonly updatedBy: string | null
  readonly isDeleted: boolean
  readonly deletedAt: string | null
  readonly deletedBy: string | null
  readonly createdAt: string
  readonly updatedAt: string
  readonly version: number
}

/**
 * Mirrors `components.schemas.MessageData` — the confirmation body
 * `DELETE /relationships/{...}/{id}` returns.
 */
export interface RelationshipActionResult {
  readonly message: string
  readonly id: string | null
}

/** Spec §7.7a: `meta.warning` on `POST /relationships/parent-child`. */
export interface MarriageWriteResult {
  readonly marriage: Marriage
  readonly warning: string | null
}

export interface ParentChildWriteResult {
  readonly parentChild: ParentChild
  readonly warning: string | null
}
