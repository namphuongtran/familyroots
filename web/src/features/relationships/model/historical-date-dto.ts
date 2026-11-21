/**
 * The wire `HistoricalDate` (docs/contracts/README.md, "HistoricalDate
 * (canonical date shape)") and the mapper into the pure domain type
 * (`@/domain/date/historical-date`).
 *
 * Duplicated from `features/persons/model/historical-date-dto.ts` per that
 * file's own instructions: `cross-feature-only-via-index` refuses the import,
 * and `src/domain/` cannot hold zod. **This is the second copy, and that was
 * the moment to turn the duplication into a `shared/` module** —
 * `shared/date/` would then host the schema, mapper, and future tree/events
 * callers alike. Not done here on purpose: the issue's own "End state" scopes
 * this slice to persons' pattern, and introducing a new `shared/` subtree is
 * a structural decision that owes its own ADR. The next slice that needs a
 * date DTO (tree, events) must do that work instead of shipping a third copy.
 */

import type { components } from '@/generated/api-types'
import type { HistoricalDate } from '@/domain/date/historical-date'
import { z } from 'zod'

const DATE_PRECISIONS = ['exact', 'year', 'month', 'circa', 'unknown'] as const

export const historicalDateDtoSchema = z.object({
  date: z.string().nullable().optional(),
  precision: z.enum(DATE_PRECISIONS),
  display: z.string().nullable().optional(),
  lunar: z.string().nullable().optional(),
})

export type HistoricalDateDto = z.infer<typeof historicalDateDtoSchema>

export function assertHistoricalDateDtoMatchesGenerated(
  dto: HistoricalDateDto,
): components['schemas']['HistoricalDate'] {
  return dto
}

export function toHistoricalDate(dto: HistoricalDateDto): HistoricalDate {
  return {
    date: dto.date ?? null,
    precision: dto.precision,
    display: dto.display ?? null,
    lunar: dto.lunar ?? null,
  }
}

export function toHistoricalDateOrNull(dto: HistoricalDateDto | undefined): HistoricalDate | null {
  return dto === undefined ? null : toHistoricalDate(dto)
}
