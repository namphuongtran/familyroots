import { describe, expect, it } from 'vitest'
import type { Person } from '@/domain/person/person'
import {
  MAX_PLAUSIBLE_YEAR,
  PERSON_FORM_ERROR_CODES,
  emptyDateGroup,
  emptyPersonFormValues,
  encodeDateGroup,
  formValuesToCreateRequest,
  formValuesToUpdateRequest,
  personFormSchema,
  personToFormValues,
  type PersonFormValues,
} from './person-form-schema'

function personFixture(overrides: Partial<Person> = {}): Person {
  return {
    id: 'p-1',
    createdByClanId: null,
    fullName: 'Trần Thị Bích',
    birthName: null,
    courtesyName: null,
    posthumousName: null,
    aliasName: null,
    gender: 'female',
    birthDate: { date: '1930-05-01', precision: 'exact', display: null, lunar: null },
    deathDate: null,
    birthPlace: null,
    deathPlace: null,
    burialPlace: null,
    tombLocation: null,
    residencePlace: null,
    religion: null,
    nationality: 'VN',
    occupation: null,
    educationLevel: null,
    titleRank: null,
    phone: null,
    email: null,
    biography: null,
    avatarUrl: null,
    notes: null,
    isDeleted: false,
    createdBy: 'u-1',
    updatedBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

function validValues(overrides: Partial<PersonFormValues> = {}): PersonFormValues {
  return { ...emptyPersonFormValues(), fullName: 'Nguyễn Văn An', ...overrides }
}

describe('personFormSchema — §7.7a validation, symbolic codes only', () => {
  it('accepts a minimal valid create (just a name)', () => {
    const result = personFormSchema.safeParse(validValues())
    expect(result.success).toBe(true)
  })

  it('rejects a blank name with the full_name_required code, not prose', () => {
    const result = personFormSchema.safeParse(validValues({ fullName: '   ' }))
    expect(result.success).toBe(false)
    const issue = result.success ? undefined : result.error.issues[0]
    expect(issue?.path).toEqual(['fullName'])
    expect(issue?.message).toBe(PERSON_FORM_ERROR_CODES.fullNameRequired)
  })

  it('requires a date when birth precision is exact', () => {
    const result = personFormSchema.safeParse(
      validValues({ birthDate: { ...emptyDateGroup(), precision: 'exact', date: '' } }),
    )
    expect(result.success).toBe(false)
    const issue = result.success ? undefined : result.error.issues[0]
    expect(issue?.path).toEqual(['birthDate', 'date'])
    expect(issue?.message).toBe(PERSON_FORM_ERROR_CODES.exactDateRequired)
  })

  it('rejects a year outside 1000–current+1', () => {
    const tooLate = String(MAX_PLAUSIBLE_YEAR + 1)
    const result = personFormSchema.safeParse(
      validValues({ birthDate: { ...emptyDateGroup(), precision: 'year', year: tooLate } }),
    )
    expect(result.success).toBe(false)
    const issue = result.success ? undefined : result.error.issues[0]
    expect(issue?.message).toBe(PERSON_FORM_ERROR_CODES.yearOutOfRange)
  })

  it('requires a month 1–12 when precision is month', () => {
    const result = personFormSchema.safeParse(
      validValues({
        birthDate: { ...emptyDateGroup(), precision: 'month', year: '1900', month: '13' },
      }),
    )
    expect(result.success).toBe(false)
    const issue = result.success ? undefined : result.error.issues[0]
    expect(issue?.path).toEqual(['birthDate', 'month'])
    expect(issue?.message).toBe(PERSON_FORM_ERROR_CODES.monthRequired)
  })

  it('never validates the death date group when hasDied is false, however malformed', () => {
    const result = personFormSchema.safeParse(
      validValues({
        hasDied: false,
        deathDate: { ...emptyDateGroup(), precision: 'exact', date: '' },
      }),
    )
    expect(result.success).toBe(true)
  })

  it('rejects a death date before an exact birth date', () => {
    const result = personFormSchema.safeParse(
      validValues({
        birthDate: { ...emptyDateGroup(), precision: 'exact', date: '1950-01-01' },
        hasDied: true,
        deathDate: { ...emptyDateGroup(), precision: 'exact', date: '1949-01-01' },
      }),
    )
    expect(result.success).toBe(false)
    const issue = result.success ? undefined : result.error.issues[0]
    expect(issue?.message).toBe(PERSON_FORM_ERROR_CODES.deathBeforeBirth)
  })

  /**
   * Negative control for the case above: a death date before birth is only
   * ever rejected when *both* sides are exact (ADR-011's own carve-out for
   * an estimate). Proves the rule discriminates rather than passing every
   * pair regardless of precision.
   */
  it('does not reject a death date before birth when either side is an estimate', () => {
    const result = personFormSchema.safeParse(
      validValues({
        birthDate: { ...emptyDateGroup(), precision: 'circa', year: '1950' },
        hasDied: true,
        deathDate: { ...emptyDateGroup(), precision: 'exact', date: '1949-01-01' },
      }),
    )
    expect(result.success).toBe(true)
  })
})

describe('encodeDateGroup', () => {
  it('exact: passes the date through untouched and ignores the default display', () => {
    const encoded = encodeDateGroup(
      { ...emptyDateGroup(), precision: 'exact', date: '1948-08-15' },
      'should not be used',
    )
    expect(encoded).toEqual({ date: '1948-08-15', precision: 'exact', display: null })
  })

  it('year: derives a Jan-1 sort date and falls back to the caller-supplied default display', () => {
    const encoded = encodeDateGroup(
      { ...emptyDateGroup(), precision: 'year', year: '1900' },
      'Năm 1900',
    )
    expect(encoded).toEqual({ date: '1900-01-01', precision: 'year', display: 'Năm 1900' })
  })

  it('year: a typed display wins over the default', () => {
    const encoded = encodeDateGroup(
      { ...emptyDateGroup(), precision: 'year', year: '1900', display: 'khoảng 1900, chưa rõ' },
      'Năm 1900',
    )
    expect(encoded.display).toBe('khoảng 1900, chưa rõ')
  })

  it('month: pads the month and derives day 1', () => {
    const encoded = encodeDateGroup(
      { ...emptyDateGroup(), precision: 'month', year: '1900', month: '3' },
      null,
    )
    expect(encoded.date).toBe('1900-03-01')
  })

  it('unknown: no date, display only if the caller supplies one', () => {
    expect(encodeDateGroup(emptyDateGroup(), null)).toEqual({
      date: null,
      precision: 'unknown',
      display: null,
    })
  })
})

describe('personToFormValues / formValuesToCreateRequest — round trip through the wire shape', () => {
  it('maps an exact birth date and no death into a create request with death fields cleared to unknown', () => {
    const person = personFixture({
      birthDate: { date: '1930-05-01', precision: 'exact', display: null, lunar: '15/04 Canh Ngọ' },
      deathDate: null,
    })
    const values = personToFormValues(person)
    expect(values.hasDied).toBe(false)

    const body = formValuesToCreateRequest(values, { birthDisplay: null, deathDisplay: null })
    expect(body.full_name).toBe('Trần Thị Bích')
    expect(body.birth_date).toBe('1930-05-01')
    expect(body.birth_date_precision).toBe('exact')
    expect(body.lunar_birth_date).toBe('15/04 Canh Ngọ')
    expect(body.death_date).toBeNull()
    expect(body.death_date_precision).toBe('unknown')
    expect(body.nationality).toBe('VN')
    expect('avatar_url' in body).toBe(false)
  })

  it('maps a circa death date, prefilling the "Đã mất" switch on', () => {
    const person = personFixture({
      deathDate: { date: '1961-01-01', precision: 'circa', display: 'khoảng 1961', lunar: null },
    })
    const values = personToFormValues(person)
    expect(values.hasDied).toBe(true)
    expect(values.deathDate.precision).toBe('circa')
    expect(values.deathDate.year).toBe('1961')
    expect(values.deathDate.display).toBe('khoảng 1961')
  })
})

describe('formValuesToUpdateRequest — clearing a death on edit sends explicit nulls, not omitted keys', () => {
  it('unchecking "Đã mất" nulls every death field rather than leaving the previous value alone', () => {
    const values = validValues({
      hasDied: false,
      deathDate: { ...emptyDateGroup(), precision: 'exact', date: '1999-01-01' },
    })
    const body = formValuesToUpdateRequest(values, 3, { birthDisplay: null, deathDisplay: null })
    expect(body.death_date).toBeNull()
    expect(body.death_date_precision).toBe('unknown')
    expect(body.death_date_display).toBeNull()
    expect(body.lunar_death_date).toBeNull()
    expect(body.expected_version).toBe(3)
  })

  it('a checked "Đã mất" sends the encoded death date', () => {
    const values = validValues({
      hasDied: true,
      deathDate: { ...emptyDateGroup(), precision: 'year', year: '1975' },
    })
    const body = formValuesToUpdateRequest(values, 1, {
      birthDisplay: null,
      deathDisplay: 'Năm 1975',
    })
    expect(body.death_date).toBe('1975-01-01')
    expect(body.death_date_precision).toBe('year')
    expect(body.death_date_display).toBe('Năm 1975')
  })
})
