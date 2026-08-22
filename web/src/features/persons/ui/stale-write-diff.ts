/**
 * The field-level comparison spec §7.7c describes: "a field-level comparison
 * list showing only the fields that actually differ ... not a full-record
 * diff," with a default choice per row — "keep mine" when the user actually
 * edited that field since it was loaded, "use latest" otherwise.
 *
 * Pure and React-free on purpose, same reasoning as `person-form-schema.ts`:
 * a three-way comparison (what the form loaded with, what the user typed,
 * what the server now holds) has no framework dependency of its own, and
 * keeping it that way is what lets `stale-write-diff.test.ts` assert on it
 * directly rather than through a rendered dialog.
 */

import type { HistoricalDate } from '@/domain/date/historical-date'
import { formatHistoricalDate } from './format-person-date'
import {
  encodeDateGroup,
  type HistoricalDateFormValue,
  type PersonFormValues,
} from './person-form-schema'
import { defaultDateDisplay, type Translate } from './date-display-defaults'

export type FieldChoice = 'mine' | 'latest'

/** Every row `diffPersonFormValues` can produce. `applyFieldChoice` below is exhaustive over this union. */
export type DiffFieldKey =
  | 'fullName'
  | 'birthName'
  | 'courtesyName'
  | 'posthumousName'
  | 'aliasName'
  | 'gender'
  | 'birthDate'
  | 'deathDate'
  | 'birthPlace'
  | 'deathPlace'
  | 'burialPlace'
  | 'tombLocation'
  | 'residencePlace'
  | 'biography'
  | 'notes'

export interface FieldDiffRow {
  /** Stable key — also the key `StaleWriteDialog` uses for its per-row segmented-control state. */
  field: DiffFieldKey
  label: string
  mine: string
  latest: string
  defaultChoice: FieldChoice
}

/**
 * The same encode a submit would run (`PersonForm.tsx`), so this dialog shows
 * exactly the text a save would store — not a re-derived approximation that
 * could disagree with it.
 */
function toHistoricalDate(t: Translate, group: HistoricalDateFormValue): HistoricalDate {
  const encoded = encodeDateGroup(group, defaultDateDisplay(t, group))
  return { date: encoded.date, precision: encoded.precision, display: encoded.display, lunar: null }
}

function renderDateGroup(t: Translate, locale: string, group: HistoricalDateFormValue): string {
  return formatHistoricalDate(toHistoricalDate(t, group), locale, t('unknown_date'))
}

interface FieldSpec {
  field: DiffFieldKey
  label: string
  value: (values: PersonFormValues) => string
}

function buildFieldSpecs(t: Translate, locale: string): FieldSpec[] {
  return [
    { field: 'fullName', label: t('full_name'), value: (v) => v.fullName.trim() },
    { field: 'birthName', label: t('birth_name'), value: (v) => v.birthName.trim() },
    { field: 'courtesyName', label: t('courtesy_name'), value: (v) => v.courtesyName.trim() },
    { field: 'posthumousName', label: t('posthumous_name'), value: (v) => v.posthumousName.trim() },
    { field: 'aliasName', label: t('alias_name'), value: (v) => v.aliasName.trim() },
    { field: 'gender', label: t('section_gender'), value: (v) => t(`gender_${v.gender}`) },
    {
      field: 'birthDate',
      label: t('section_birth'),
      value: (v) => renderDateGroup(t, locale, v.birthDate),
    },
    {
      field: 'deathDate',
      label: t('section_death'),
      value: (v) => (v.hasDied ? renderDateGroup(t, locale, v.deathDate) : t('alive')),
    },
    { field: 'birthPlace', label: t('birth_place'), value: (v) => v.birthPlace.trim() },
    { field: 'deathPlace', label: t('death_place'), value: (v) => v.deathPlace.trim() },
    { field: 'burialPlace', label: t('burial_place'), value: (v) => v.burialPlace.trim() },
    { field: 'tombLocation', label: t('tomb_location'), value: (v) => v.tombLocation.trim() },
    { field: 'residencePlace', label: t('residence_place'), value: (v) => v.residencePlace.trim() },
    { field: 'biography', label: t('section_biography'), value: (v) => v.biography.trim() },
    { field: 'notes', label: t('section_notes'), value: (v) => v.notes.trim() },
  ]
}

/**
 * `original` is the snapshot the form was loaded with (before the user
 * typed anything this session); `mine` is the form's current values at the
 * moment the save 409'd; `latest` is the freshly refetched record, mapped
 * through the same `personToFormValues`. Only rows where `mine` and `latest`
 * render differently are returned, per spec §7.7c.
 */
export function diffPersonFormValues(
  t: Translate,
  locale: string,
  original: PersonFormValues,
  mine: PersonFormValues,
  latest: PersonFormValues,
): FieldDiffRow[] {
  const rows: FieldDiffRow[] = []
  for (const spec of buildFieldSpecs(t, locale)) {
    const mineValue = spec.value(mine)
    const latestValue = spec.value(latest)
    if (mineValue === latestValue) continue
    const originalValue = spec.value(original)
    rows.push({
      field: spec.field,
      label: spec.label,
      mine: mineValue,
      latest: latestValue,
      defaultChoice: mineValue !== originalValue ? 'mine' : 'latest',
    })
  }
  return rows
}

/**
 * Copies one field's *encoded* value from `source` onto `target`, mutating
 * `target` in place — `StaleWriteDialog`'s "Lưu bản đã chọn" applies one of
 * these per row whose choice is `'latest'`. Written as an exhaustive switch
 * over {@link DiffFieldKey} rather than `target[field] = source[field]`
 * (which would need an `any` cast, since the two sides' value types differ
 * per key) and rather than a lookup table, so a `DiffFieldKey` added to the
 * union without a case here fails `pnpm type-check` instead of silently
 * doing nothing at runtime.
 *
 * `'deathDate'` copies two `PersonFormValues` keys, not one — the diff row
 * itself renders the *combination* of `hasDied` and `deathDate` as a single
 * comparison (an alive `mine` against a dated `latest`, or the reverse), so
 * choosing "latest" for that row has to bring both back in sync or the
 * merged form could claim the person is dead while `hasDied` is still false.
 */
export function applyFieldChoice(
  target: PersonFormValues,
  source: PersonFormValues,
  field: DiffFieldKey,
): void {
  switch (field) {
    case 'fullName':
      target.fullName = source.fullName
      return
    case 'birthName':
      target.birthName = source.birthName
      return
    case 'courtesyName':
      target.courtesyName = source.courtesyName
      return
    case 'posthumousName':
      target.posthumousName = source.posthumousName
      return
    case 'aliasName':
      target.aliasName = source.aliasName
      return
    case 'gender':
      target.gender = source.gender
      return
    case 'birthDate':
      target.birthDate = source.birthDate
      return
    case 'deathDate':
      target.hasDied = source.hasDied
      target.deathDate = source.deathDate
      return
    case 'birthPlace':
      target.birthPlace = source.birthPlace
      return
    case 'deathPlace':
      target.deathPlace = source.deathPlace
      return
    case 'burialPlace':
      target.burialPlace = source.burialPlace
      return
    case 'tombLocation':
      target.tombLocation = source.tombLocation
      return
    case 'residencePlace':
      target.residencePlace = source.residencePlace
      return
    case 'biography':
      target.biography = source.biography
      return
    case 'notes':
      target.notes = source.notes
      return
  }
}

/**
 * A plain-text "label: value" dump of every field the form holds, for the
 * §7.7c "Sao chép nội dung của tôi" escape hatch — the user's own typing,
 * safe to paste elsewhere, independent of whether any field actually
 * conflicts. Reuses the same field list and rendering as the diff itself so
 * the copied text never disagrees with what the dialog shows.
 */
export function personFormValuesSummary(
  t: Translate,
  locale: string,
  values: PersonFormValues,
): string {
  return buildFieldSpecs(t, locale)
    .map((spec) => `${spec.label}: ${spec.value(values) || t('empty_value_placeholder')}`)
    .join('\n')
}
