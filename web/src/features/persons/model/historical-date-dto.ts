/**
 * The wire `HistoricalDate` (docs/contracts/README.md, "HistoricalDate
 * (canonical date shape)") and the mapper into the pure domain type
 * (`@/domain/date/historical-date`).
 *
 * This schema is `persons`-local on purpose, not because the shape is
 * `persons`-specific — every future slice that carries a date (marriages,
 * events, tree nodes) parses the exact same wire object. `src/domain/` cannot
 * hold it (no zod allowed there), and `src/shared/` today is only
 * `http/`, `telemetry/`, and `testing/` (`web/CLAUDE.md`, "Architecture") —
 * adding a new `shared/` subtree is a structural decision this seed does not
 * make alone. So: **the next slice that needs a date DTO copies this file
 * rather than importing it from here** (`cross-feature-only-via-index` would
 * refuse the import anyway, since this file is not `persons/index.ts`), and
 * whoever copies it a second time should turn the duplication into a real
 * `shared/` module instead of a third copy.
 */

import type { components } from '@/generated/api-types'
import type { HistoricalDate } from '@/domain/date/historical-date'
import { z } from 'zod'

/** `HistoricalDate.precision` in docs/contracts/README.md, "HistoricalDate". */
const DATE_PRECISIONS = ['exact', 'year', 'month', 'circa', 'unknown'] as const

/**
 * The generated type widens `precision` to a bare `string` (openapi-typescript
 * cannot see through the backend's regex-pattern constraint into an enum), so
 * this schema is what narrows it back — and rejects a value outside the five
 * the contract defines, rather than silently passing one through.
 */
export const historicalDateDtoSchema = z.object({
  date: z.string().nullable().optional(),
  precision: z.enum(DATE_PRECISIONS),
  display: z.string().nullable().optional(),
  lunar: z.string().nullable().optional(),
})

export type HistoricalDateDto = z.infer<typeof historicalDateDtoSchema>

/**
 * Compile-time contract check: this only type-checks while `HistoricalDateDto`
 * stays assignable to the generated `HistoricalDate` shape. A backend change
 * that adds a required field, or narrows/widens an existing one
 * incompatibly, fails `pnpm type-check` here — not at runtime.
 */
export function assertHistoricalDateDtoMatchesGenerated(
  dto: HistoricalDateDto,
): components['schemas']['HistoricalDate'] {
  return dto
}

/**
 * `date`, `display`, and `lunar` are optional on the wire — the key can be
 * missing entirely, not just `null`. The domain type only ever thinks about
 * one absent value (`null`), per `historical-date.ts`'s own doc comment, so
 * this is the one place that normalises "missing" into "null".
 */
export function toHistoricalDate(dto: HistoricalDateDto): HistoricalDate {
  return {
    date: dto.date ?? null,
    precision: dto.precision,
    display: dto.display ?? null,
    lunar: dto.lunar ?? null,
  }
}

/** `birth_date` / `death_date` on `PersonResponse` are optional (absent under `fields=`). */
export function toHistoricalDateOrNull(dto: HistoricalDateDto | undefined): HistoricalDate | null {
  return dto === undefined ? null : toHistoricalDate(dto)
}
