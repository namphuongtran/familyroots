/**
 * The relationship editor's pure decisions (#328), kept React-free so a unit test can read them
 * directly: which `spouse_order` a new spouse gets, which marriages the reorder list holds, the
 * PATCH sequence one up/down press sends, and how a `422 relationship.parent_too_young` reads.
 */

import type { Marriage } from '@/domain/relationship/relationship'
import { ApiError } from '@/shared/http/errors'

export const PARENT_TOO_YOUNG_CODE = 'relationship.parent_too_young'
export const STALE_WRITE_CODE = 'stale_write'

/**
 * The marriages that hold a rank. `divorced` is the one status the backend's
 * `duplicate_spouse_order` check exempts (docs/contracts/rest-relationships-api.md, ADR-029), so
 * a divorced spouse keeps no place in the order and is not reordered.
 */
export function rankedMarriages(marriages: readonly Marriage[]): Marriage[] {
  return marriages
    .filter((m) => m.status !== 'divorced')
    .sort((a, b) => {
      if (a.spouseOrder === null && b.spouseOrder === null) return 0
      if (a.spouseOrder === null) return 1
      if (b.spouseOrder === null) return -1
      return a.spouseOrder - b.spouseOrder
    })
}

/** The prefill for a new spouse: one past the highest rank held, `1` when none is. */
export function nextSpouseOrder(marriages: readonly Marriage[]): number {
  let max = 0
  for (const m of rankedMarriages(marriages)) {
    if (m.spouseOrder !== null && m.spouseOrder > max) max = m.spouseOrder
  }
  return max + 1
}

/**
 * One `PATCH /relationships/marriages/{id}` in a reorder. `expectedVersion` is `'chained'` when
 * the step writes a marriage an earlier step of the same plan already wrote, so its version is
 * the one that earlier response carried, not the one the list was read at.
 */
export interface ReorderStep {
  readonly marriageId: string
  readonly spouseOrder: number | null
  readonly expectedVersion: number | 'chained'
}

/**
 * The writes that swap `ranked[index]` with its neighbour in `direction`.
 *
 * **Three writes, not two, when both ranks are numbers.** The backend refuses a marriage whose
 * new `spouse_order` another live marriage of either spouse already holds
 * (`relationship.duplicate_spouse_order`, 409), and it checks each PATCH on its own. So writing
 * wife B to 1 while wife A still holds 1 is refused. The first write parks A at `null`, which
 * the check skips, then B takes A's rank, then A takes B's. When one of the two holds no rank,
 * nothing needs parking and the swap is two writes.
 *
 * Returns `[]` when there is no neighbour in that direction.
 */
export function planSpouseReorder(
  ranked: readonly Marriage[],
  index: number,
  direction: 'up' | 'down',
): ReorderStep[] {
  const other = direction === 'up' ? index - 1 : index + 1
  if (index < 0 || index >= ranked.length || other < 0 || other >= ranked.length) return []
  const moving = ranked[index]
  const neighbour = ranked[other]
  const movingOrder = moving.spouseOrder
  const neighbourOrder = neighbour.spouseOrder

  if (movingOrder !== null && neighbourOrder !== null) {
    return [
      { marriageId: neighbour.id, spouseOrder: null, expectedVersion: neighbour.version },
      { marriageId: moving.id, spouseOrder: neighbourOrder, expectedVersion: moving.version },
      { marriageId: neighbour.id, spouseOrder: movingOrder, expectedVersion: 'chained' },
    ]
  }
  // At most one of the two holds a rank: vacate it first, then hand it over.
  const holder = movingOrder !== null ? moving : neighbour
  const taker = holder === moving ? neighbour : moving
  return [
    { marriageId: holder.id, spouseOrder: null, expectedVersion: holder.version },
    { marriageId: taker.id, spouseOrder: holder.spouseOrder, expectedVersion: taker.version },
  ]
}

/** `detail.min_age_gap` and `detail.actual` off a `422 relationship.parent_too_young`, or `null`. */
export function parentTooYoungDetail(
  error: unknown,
): { minAgeGap: number | string; actual: number | string } | null {
  if (!(error instanceof ApiError) || error.code !== PARENT_TOO_YOUNG_CODE) return null
  const { min_age_gap: minAgeGap, actual } = error.detail
  const readable = (v: unknown) => (typeof v === 'number' || typeof v === 'string' ? v : '?')
  return { minAgeGap: readable(minAgeGap), actual: readable(actual) }
}

export function isStaleWrite(error: unknown): error is ApiError {
  return error instanceof ApiError && error.code === STALE_WRITE_CODE
}
