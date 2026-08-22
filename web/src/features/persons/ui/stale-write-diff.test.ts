import { describe, expect, it } from 'vitest'
import { emptyDateGroup, emptyPersonFormValues, type PersonFormValues } from './person-form-schema'
import { applyFieldChoice, diffPersonFormValues, personFormValuesSummary } from './stale-write-diff'

/** A tiny, literal stand-in for `useTranslations` — every key it needs, nothing invented beyond that. */
const MESSAGES: Record<string, string> = {
  full_name: 'Họ và tên',
  birth_name: 'Tên khai sinh',
  courtesy_name: 'Tên chữ',
  posthumous_name: 'Tên hiệu',
  alias_name: 'Tên gọi khác',
  section_gender: 'Giới tính',
  gender_male: 'Nam',
  gender_female: 'Nữ',
  gender_unknown: 'Không rõ',
  section_birth: 'Ngày sinh',
  section_death: 'Ngày mất',
  birth_place: 'Nơi sinh',
  death_place: 'Nơi mất',
  burial_place: 'Nơi chôn cất',
  tomb_location: 'Vị trí mộ',
  residence_place: 'Nơi cư trú',
  section_biography: 'Tiểu sử',
  section_notes: 'Ghi chú',
  alive: 'Còn sống',
  unknown_date: 'Không rõ',
  default_display_year: 'Năm {year}',
  default_display_month: 'Tháng {month}/{year}',
  default_display_circa: 'khoảng {year}',
  empty_value_placeholder: '(để trống)',
}

function t(key: string, values: Record<string, string | number> = {}): string {
  const template = MESSAGES[key] ?? key
  return Object.entries(values).reduce(
    (acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)),
    template,
  )
}

function values(overrides: Partial<PersonFormValues> = {}): PersonFormValues {
  return { ...emptyPersonFormValues(), fullName: 'Nguyễn Văn An', ...overrides }
}

describe('diffPersonFormValues — spec §7.7c: only rows that actually differ, defaulted from what the user touched', () => {
  it('returns no rows when mine and latest render identically', () => {
    const same = values()
    const rows = diffPersonFormValues(t, 'vi', same, same, same)
    expect(rows).toEqual([])
  })

  it('a field mine changed from the original defaults to "keep mine"', () => {
    const original = values({ birthPlace: 'Hà Nội' })
    const mine = values({ birthPlace: 'Huế' })
    const latest = values({ birthPlace: 'Hà Nội' })

    const rows = diffPersonFormValues(t, 'vi', original, mine, latest)
    const row = rows.find((r) => r.field === 'birthPlace')
    expect(row).toMatchObject({ mine: 'Huế', latest: 'Hà Nội', defaultChoice: 'mine' })
  })

  it('a field mine never touched defaults to "use latest"', () => {
    const original = values({ birthPlace: 'Hà Nội' })
    const mine = values({ birthPlace: 'Hà Nội' })
    const latest = values({ birthPlace: 'Đà Nẵng' })

    const rows = diffPersonFormValues(t, 'vi', original, mine, latest)
    const row = rows.find((r) => r.field === 'birthPlace')
    expect(row).toMatchObject({ mine: 'Hà Nội', latest: 'Đà Nẵng', defaultChoice: 'latest' })
  })

  /**
   * Negative control: a naive "did the field change from latest" reading
   * (rather than "did the field change from what I started with") would
   * default *every* differing row to "keep mine", because `mine` always
   * differs from `latest` by construction of the filter above. This test
   * fails under that reading and passes under the spec's own rule.
   */
  it('a field the user never edited still defaults to "use latest" even though it differs from mine', () => {
    const original = values({ notes: 'ghi chú gốc' })
    const mine = values({ notes: 'ghi chú gốc' })
    const latest = values({ notes: 'người khác vừa thêm dòng này' })

    const rows = diffPersonFormValues(t, 'vi', original, mine, latest)
    const row = rows.find((r) => r.field === 'notes')
    expect(row?.defaultChoice).toBe('latest')
  })

  it('renders the death date through the same domain render rule the rest of the app uses', () => {
    const original = values({ hasDied: false })
    const mine = values({
      hasDied: true,
      deathDate: { precision: 'circa', date: '', year: '1961', month: '', display: '', lunar: '' },
    })
    const latest = values({
      hasDied: true,
      deathDate: {
        precision: 'exact',
        date: '1961-11-15',
        year: '',
        month: '',
        display: '',
        lunar: '',
      },
    })

    const rows = diffPersonFormValues(t, 'vi', original, mine, latest)
    const row = rows.find((r) => r.field === 'deathDate')
    expect(row?.mine).toBe('khoảng 1961')
    expect(row?.latest).toBe('15/11/1961')
    expect(row?.defaultChoice).toBe('mine')
  })

  it('an alive person compares against "Còn sống", not an empty string', () => {
    const original = values({ hasDied: false })
    const mine = values({ hasDied: false })
    const latest = values({
      hasDied: true,
      deathDate: {
        precision: 'exact',
        date: '2026-01-01',
        year: '',
        month: '',
        display: '',
        lunar: '',
      },
    })

    const rows = diffPersonFormValues(t, 'vi', original, mine, latest)
    const row = rows.find((r) => r.field === 'deathDate')
    expect(row?.mine).toBe('Còn sống')
  })
})

describe('applyFieldChoice — "Lưu bản đã chọn" merges one field at a time', () => {
  it('copies a plain string field', () => {
    const target = values({ birthPlace: 'Huế' })
    const source = values({ birthPlace: 'Hà Nội' })
    applyFieldChoice(target, source, 'birthPlace')
    expect(target.birthPlace).toBe('Hà Nội')
  })

  it('"deathDate" brings hasDied and deathDate back in sync together', () => {
    const target = values({ hasDied: false })
    const source = values({
      hasDied: true,
      deathDate: { ...emptyDateGroup(), precision: 'year', year: '1980' },
    })
    applyFieldChoice(target, source, 'deathDate')
    expect(target.hasDied).toBe(true)
    expect(target.deathDate.year).toBe('1980')
  })

  /**
   * Negative control: if `'deathDate'` only copied the `deathDate` group and
   * forgot `hasDied`, this would leave `hasDied: false` with a populated
   * `deathDate` group underneath it — a state `formValuesToUpdateRequest`
   * reads as "alive" regardless of what `deathDate` holds. This test fails
   * under that half-copy and passes under the real implementation.
   */
  it('never leaves hasDied false with a populated deathDate group after choosing latest', () => {
    const target = values({ hasDied: false, deathDate: emptyDateGroup() })
    const source = values({
      hasDied: true,
      deathDate: { ...emptyDateGroup(), precision: 'exact', date: '1980-01-01' },
    })
    applyFieldChoice(target, source, 'deathDate')
    expect(target.hasDied).toBe(true)
  })
})

describe('personFormValuesSummary — the "Sao chép nội dung của tôi" escape hatch', () => {
  it('renders one "label: value" line per field, in the same order as the diff', () => {
    const summary = personFormValuesSummary(t, 'vi', values({ birthPlace: 'Huế' }))
    const lines = summary.split('\n')
    expect(lines[0]).toBe('Họ và tên: Nguyễn Văn An')
    expect(lines).toContain('Nơi sinh: Huế')
  })
})
