import { describe, expect, it } from 'vitest'
import {
  historicalDateSortKey,
  lunarLabel,
  renderHistoricalDate,
  type HistoricalDate,
} from './historical-date'

// `display: null`, not `''`: the backend types it `string | null` and marks it
// optional, so null is the real absent value and the factory should produce it.
function date(overrides: Partial<HistoricalDate> = {}): HistoricalDate {
  return { date: null, precision: 'unknown', display: null, lunar: null, ...overrides }
}

describe('renderHistoricalDate', () => {
  it('renders the ISO date when precision is exact', () => {
    const result = renderHistoricalDate(date({ date: '1950-03-12', precision: 'exact' }))
    expect(result).toEqual({ kind: 'exact', iso: '1950-03-12' })
  })

  it('prefers the human display string for every inexact precision', () => {
    for (const precision of ['year', 'month', 'circa', 'unknown'] as const) {
      const result = renderHistoricalDate(
        date({ date: '1750-01-01', precision, display: 'khoảng 1750' }),
      )
      expect(result).toEqual({ kind: 'text', text: 'khoảng 1750' })
    }
  })

  it('falls back to the ISO date when an inexact value has no display text', () => {
    const result = renderHistoricalDate(date({ date: '1750-01-01', precision: 'circa' }))
    expect(result).toEqual({ kind: 'exact', iso: '1750-01-01' })
  })

  it('falls back to display when precision is exact but the date is missing', () => {
    // Defensive: the backend should not produce this, but a null date with
    // precision "exact" must not render as an empty cell.
    const result = renderHistoricalDate(date({ precision: 'exact', display: 'không rõ' }))
    expect(result).toEqual({ kind: 'text', text: 'không rõ' })
  })

  it('reports unknown for null, undefined, and a fully empty value', () => {
    expect(renderHistoricalDate(null)).toEqual({ kind: 'unknown' })
    expect(renderHistoricalDate(undefined)).toEqual({ kind: 'unknown' })
    expect(renderHistoricalDate(date())).toEqual({ kind: 'unknown' })
  })

  it('ignores a display string that is only whitespace', () => {
    expect(renderHistoricalDate(date({ precision: 'circa', display: '   ' }))).toEqual({
      kind: 'unknown',
    })
  })
})

describe('historicalDateSortKey', () => {
  it('orders by the best-known point regardless of precision', () => {
    const older = historicalDateSortKey(date({ date: '1900-01-01', precision: 'circa' }))
    const newer = historicalDateSortKey(date({ date: '1950-01-01', precision: 'exact' }))
    expect(older).not.toBeNull()
    expect(newer).not.toBeNull()
    expect(older as number).toBeLessThan(newer as number)
  })

  it('returns null when there is no point to sort by', () => {
    expect(historicalDateSortKey(date({ display: 'khoảng thời Nguyễn' }))).toBeNull()
    expect(historicalDateSortKey(null)).toBeNull()
  })

  it('returns null for an unparseable date rather than NaN', () => {
    expect(historicalDateSortKey(date({ date: 'not-a-date', precision: 'exact' }))).toBeNull()
  })
})

describe('lunarLabel', () => {
  it('returns the lunar string when present', () => {
    expect(lunarLabel(date({ lunar: '15/08 Nhâm Tý' }))).toBe('15/08 Nhâm Tý')
  })

  it('returns null when absent or blank', () => {
    expect(lunarLabel(date())).toBeNull()
    expect(lunarLabel(date({ lunar: '  ' }))).toBeNull()
    expect(lunarLabel(null)).toBeNull()
  })
})
