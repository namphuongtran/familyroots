/**
 * The canonical genealogical date (ADR-011, docs/contracts/README.md).
 *
 * Pure domain: this module decides *what* to show, never *how* to format it.
 * Locale formatting is a presentation concern, so an exact date comes back as an
 * ISO string for the UI to run through Intl — that keeps this file free of any
 * framework or locale dependency and makes the rule testable in isolation.
 */

export type DatePrecision = 'exact' | 'year' | 'month' | 'circa' | 'unknown'

/**
 * Mirrors `components.schemas.HistoricalDate` in the backend OpenAPI document,
 * which types `date`, `display` and `lunar` as `string | null` **and** marks all
 * three optional. The DTO mapper normalises a missing key to null so this model
 * only ever has to think about one absent value.
 *
 * `precision` is narrower here than on the wire: the schema is a pattern-
 * constrained `string`, so the generated type is a bare `string` and the
 * hand-written Zod schema at the boundary is what narrows it to this union.
 */
export interface HistoricalDate {
  /** ISO date or null — the best-known point, used for sorting and anniversaries. */
  readonly date: string | null
  readonly precision: DatePrecision
  /** Human text, e.g. "khoảng 1750". Null when the backend has nothing to say. */
  readonly display: string | null
  /** Display-only lunar string, e.g. "15/08 Nhâm Tý". */
  readonly lunar: string | null
}

export type RenderedDate =
  { kind: 'exact'; iso: string } | { kind: 'text'; text: string } | { kind: 'unknown' }

function nonBlank(value: string | null | undefined): string | null {
  if (value == null) return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * Contract rule: render `date` when precision is "exact", otherwise `display`,
 * falling back to `date`.
 */
export function renderHistoricalDate(value: HistoricalDate | null | undefined): RenderedDate {
  if (value == null) return { kind: 'unknown' }

  const iso = nonBlank(value.date)
  const display = nonBlank(value.display)

  if (value.precision === 'exact' && iso !== null) return { kind: 'exact', iso }
  if (display !== null) return { kind: 'text', text: display }
  if (iso !== null) return { kind: 'exact', iso }
  return { kind: 'unknown' }
}

/**
 * Sortable point in time, or null when the value carries none. Null rather than
 * NaN or Infinity so callers must decide where undated entries belong instead of
 * silently sorting them to one end.
 */
export function historicalDateSortKey(value: HistoricalDate | null | undefined): number | null {
  const iso = nonBlank(value?.date)
  if (iso === null) return null
  const parsed = Date.parse(iso)
  return Number.isNaN(parsed) ? null : parsed
}

export function lunarLabel(value: HistoricalDate | null | undefined): string | null {
  return nonBlank(value?.lunar)
}
