import { describe, expect, it } from 'vitest'
import type { HistoricalDate } from '@/domain/date/historical-date'
import { formatHistoricalDate, isKnownDate, personHasVisibleDetail } from './format-person-date'

function date(overrides: Partial<HistoricalDate>): HistoricalDate {
  return { date: null, precision: 'unknown', display: null, lunar: null, ...overrides }
}

describe('formatHistoricalDate', () => {
  it('formats an exact date through Intl rather than printing the raw ISO string', () => {
    const result = formatHistoricalDate(
      date({ date: '1948-08-15', precision: 'exact', display: 'irrelevant' }),
      'vi',
      'Không rõ',
    )
    // Negative control for this assertion: swapping in the raw ISO string
    // ('1948-08-15') would leave the render-rule precedence unverified —
    // exact must prefer `date`, and only Intl formatting proves the value
    // that reached the screen is a formatted date, not the wire string.
    expect(result).toBe('15/08/1948')
  })

  it('falls back to `display` for a non-exact precision, per the contract precedence', () => {
    const result = formatHistoricalDate(
      date({ date: '1961-01-01', precision: 'circa', display: 'khoảng 1961' }),
      'vi',
      'Không rõ',
    )
    expect(result).toBe('khoảng 1961')
  })

  it('falls back to the unknown label when neither date nor display is present', () => {
    expect(formatHistoricalDate(date({}), 'vi', 'Không rõ')).toBe('Không rõ')
    expect(formatHistoricalDate(null, 'vi', 'Không rõ')).toBe('Không rõ')
  })

  it('falls back to the raw iso when display is blank but precision is exact', () => {
    const result = formatHistoricalDate(
      date({ date: '1892-03-02', precision: 'exact', display: '  ' }),
      'en',
      'Unknown',
    )
    expect(result).toBe('03/02/1892')
  })
})

describe('isKnownDate', () => {
  it('is true whenever the render rule resolves to exact or text', () => {
    expect(isKnownDate(date({ date: '1892-01-01', precision: 'year', display: '1892' }))).toBe(true)
    expect(isKnownDate(date({ date: '1892-01-01', precision: 'exact' }))).toBe(true)
  })

  it('is false for an unknown precision with nothing to show', () => {
    // Negative control: this is the exact case the caller (PersonRow) uses to
    // decide "show a lifespan range" vs "show a born-only line" — if this
    // flipped to true for an empty date, a living person with no birth date
    // recorded would misreport a death.
    expect(isKnownDate(date({}))).toBe(false)
    expect(isKnownDate(null)).toBe(false)
    expect(isKnownDate(undefined)).toBe(false)
  })
})

function bareNamePerson(): Parameters<typeof personHasVisibleDetail>[0] {
  return {
    birthName: null,
    courtesyName: null,
    posthumousName: null,
    aliasName: null,
    titleRank: null,
    birthPlace: null,
    deathPlace: null,
    residencePlace: null,
    burialPlace: null,
    tombLocation: null,
    birthDate: null,
    deathDate: null,
    biography: null,
    notes: null,
  }
}

describe('personHasVisibleDetail', () => {
  it("is false for a person with nothing but a name — spec §7.6's sparse-record case", () => {
    // Negative control: a version of this function that always returned
    // `true` would never trigger the sparse-record collapse `PersonProfile`
    // renders for exactly this shape, and a version that always returned
    // `false` would collapse every profile, including ones with real data —
    // both are checked below by the other cases in this block.
    expect(personHasVisibleDetail(bareNamePerson())).toBe(false)
  })

  it('is true when any single name field is present', () => {
    expect(personHasVisibleDetail({ ...bareNamePerson(), courtesyName: 'Văn An' })).toBe(true)
  })

  it('is true when any single place field is present', () => {
    expect(personHasVisibleDetail({ ...bareNamePerson(), residencePlace: 'Hà Nội' })).toBe(true)
  })

  it('is true when a date is known, even with every text field blank', () => {
    expect(
      personHasVisibleDetail({
        ...bareNamePerson(),
        birthDate: date({ date: '1900-01-01', precision: 'year', display: '1900' }),
      }),
    ).toBe(true)
  })

  it('is true when biography or notes is present', () => {
    expect(personHasVisibleDetail({ ...bareNamePerson(), biography: 'Một câu chuyện dài.' })).toBe(
      true,
    )
    expect(personHasVisibleDetail({ ...bareNamePerson(), notes: 'Ghi chú nội bộ.' })).toBe(true)
  })
})
