/**
 * The `PersonForm` (S-032) form values, its zod validation, and the pure
 * mappers to and from the wire request/response shapes.
 *
 * Deliberately not `model/` — that directory holds zod DTOs for *wire*
 * shapes, constrained to the generated OpenAPI types
 * (`person-dto.ts`'s own header comment). A form's local shape is neither:
 * it is UI state a person types into, shaped for editing rather than for the
 * wire, and it is validated against itself, not against a backend contract.
 * `web/CLAUDE.md`'s "State management split" already names the pattern this
 * follows — "Forms: react-hook-form + zod resolvers" — and the legacy
 * `src/lib/validations/member.schema.ts` is the same idea for the form this
 * one replaces.
 *
 * **Every zod `message` here is a symbolic code, never prose.** The root
 * `CLAUDE.md` rule is "no user-facing string is hardcoded — everything goes
 * through next-intl," and a validation message is exactly that: it renders
 * on screen. `PersonForm.tsx` maps each code through `useTranslations` before
 * showing it. The legacy schema this replaces hardcoded Vietnamese directly
 * into `.refine()` — do not copy that pattern.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { Gender, Person } from '@/domain/person/person'
import type { DatePrecision, HistoricalDate } from '@/domain/date/historical-date'

type PersonCreateRequest = components['schemas']['PersonCreateRequest']
type PersonUpdateRequest = components['schemas']['PersonUpdateRequest']

/**
 * ADR-011 §7.7a: "year plausibility (1000–current+1)". `CURRENT_YEAR` is read
 * once at module load — this only ever needs to be right to the calendar
 * year, and re-reading `Date.now()` per validation would make the same input
 * flip from valid to invalid at midnight on New Year's Eve with no code
 * change, which is a worse property than being one year stale for however
 * long a server process lives.
 */
const CURRENT_YEAR = new Date().getUTCFullYear()
export const MIN_PLAUSIBLE_YEAR = 1000
export const MAX_PLAUSIBLE_YEAR = CURRENT_YEAR + 1

const GENDERS = ['male', 'female', 'unknown'] as const
const PRECISIONS = ['exact', 'year', 'month', 'circa', 'unknown'] as const

/** Validation error codes `PersonForm.tsx` maps to a translated string. Never rendered directly. */
export const PERSON_FORM_ERROR_CODES = {
  fullNameRequired: 'full_name_required',
  exactDateRequired: 'exact_date_required',
  yearRequired: 'year_required',
  monthRequired: 'month_required',
  yearOutOfRange: 'year_out_of_range',
  deathBeforeBirth: 'death_before_birth',
} as const

/**
 * One `HistoricalDate` group as the form edits it. `date`/`year`/`month` are
 * plain strings (never numbers) because they are controlled-input values —
 * an empty string is "not typed yet", which `z.coerce.number()` cannot tell
 * apart from `0`. Only the sub-field the active `precision` actually uses is
 * validated; the other two are simply ignored by `encodeDateGroup` below,
 * same as the backend ignores a `*_display` it was not asked to interpret.
 */
export interface HistoricalDateFormValue {
  precision: DatePrecision
  /** `YYYY-MM-DD`, used only when `precision === 'exact'`. */
  date: string
  /** Digits, used when `precision` is `year`, `month`, or `circa`. */
  year: string
  /** `1`-`12`, used only when `precision === 'month'`. */
  month: string
  /** Free text. Rendered instead of `date` whenever `precision !== 'exact'` (the domain render rule). */
  display: string
  /** Display-only lunar string (ADR-018) — independent of `precision`. */
  lunar: string
}

export function emptyDateGroup(): HistoricalDateFormValue {
  return { precision: 'unknown', date: '', year: '', month: '', display: '', lunar: '' }
}

export interface PersonFormValues {
  fullName: string
  birthName: string
  courtesyName: string
  posthumousName: string
  aliasName: string
  gender: Gender
  birthDate: HistoricalDateFormValue
  /** Reveals the death-date group (spec §7.7's "Đã mất switch"). Not itself sent to the wire. */
  hasDied: boolean
  deathDate: HistoricalDateFormValue
  birthPlace: string
  deathPlace: string
  burialPlace: string
  tombLocation: string
  residencePlace: string
  biography: string
  notes: string
}

function isDigits(value: string): boolean {
  return /^\d{1,4}$/.test(value.trim())
}

/**
 * One date group's own issues, independent of zod — kept as a plain function
 * so `person-form-schema.test.ts` can assert on it directly, and so the two
 * call sites below (birth, always checked; death, checked only when
 * `hasDied`) share one rule rather than drifting.
 */
function dateGroupIssues(
  group: HistoricalDateFormValue,
): Array<{ path: Array<string>; code: string }> {
  const issues: Array<{ path: Array<string>; code: string }> = []
  switch (group.precision) {
    case 'exact': {
      if (group.date.trim().length === 0) {
        issues.push({ path: ['date'], code: PERSON_FORM_ERROR_CODES.exactDateRequired })
        break
      }
      const year = Number(group.date.slice(0, 4))
      if (year < MIN_PLAUSIBLE_YEAR || year > MAX_PLAUSIBLE_YEAR) {
        issues.push({ path: ['date'], code: PERSON_FORM_ERROR_CODES.yearOutOfRange })
      }
      break
    }
    case 'year':
    case 'circa': {
      if (!isDigits(group.year)) {
        issues.push({ path: ['year'], code: PERSON_FORM_ERROR_CODES.yearRequired })
        break
      }
      const year = Number(group.year.trim())
      if (year < MIN_PLAUSIBLE_YEAR || year > MAX_PLAUSIBLE_YEAR) {
        issues.push({ path: ['year'], code: PERSON_FORM_ERROR_CODES.yearOutOfRange })
      }
      break
    }
    case 'month': {
      if (!isDigits(group.year)) {
        issues.push({ path: ['year'], code: PERSON_FORM_ERROR_CODES.yearRequired })
      } else {
        const year = Number(group.year.trim())
        if (year < MIN_PLAUSIBLE_YEAR || year > MAX_PLAUSIBLE_YEAR) {
          issues.push({ path: ['year'], code: PERSON_FORM_ERROR_CODES.yearOutOfRange })
        }
      }
      const month = Number(group.month.trim())
      if (!Number.isInteger(month) || month < 1 || month > 12) {
        issues.push({ path: ['month'], code: PERSON_FORM_ERROR_CODES.monthRequired })
      }
      break
    }
    case 'unknown':
      break
  }
  return issues
}

/**
 * Exact-date-only comparison, per spec §7.7a: "death not before birth when
 * both are exact". An estimated pair (either side `year`/`month`/`circa`/
 * `unknown`) never raises this — the same carve-out
 * `docs/contracts/error-codes.md`'s `relationship.parent_too_young` makes for
 * an age-gap check, and ADR-011's own reasoning: an estimate is not a claim
 * precise enough to fail a strict ordering check against.
 */
function isDeathBeforeBirth(
  birth: HistoricalDateFormValue,
  death: HistoricalDateFormValue,
): boolean {
  if (birth.precision !== 'exact' || death.precision !== 'exact') return false
  if (!birth.date || !death.date) return false
  return death.date < birth.date
}

const historicalDateGroupShape = z.object({
  precision: z.enum(PRECISIONS),
  date: z.string(),
  year: z.string(),
  month: z.string(),
  display: z.string(),
  lunar: z.string(),
})

export const personFormSchema = z
  .object({
    fullName: z.string(),
    birthName: z.string(),
    courtesyName: z.string(),
    posthumousName: z.string(),
    aliasName: z.string(),
    gender: z.enum(GENDERS),
    birthDate: historicalDateGroupShape,
    hasDied: z.boolean(),
    deathDate: historicalDateGroupShape,
    birthPlace: z.string(),
    deathPlace: z.string(),
    burialPlace: z.string(),
    tombLocation: z.string(),
    residencePlace: z.string(),
    biography: z.string(),
    notes: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.fullName.trim().length === 0) {
      ctx.addIssue({
        code: 'custom',
        path: ['fullName'],
        message: PERSON_FORM_ERROR_CODES.fullNameRequired,
      })
    }

    for (const issue of dateGroupIssues(values.birthDate)) {
      ctx.addIssue({ code: 'custom', path: ['birthDate', ...issue.path], message: issue.code })
    }

    if (values.hasDied) {
      for (const issue of dateGroupIssues(values.deathDate)) {
        ctx.addIssue({ code: 'custom', path: ['deathDate', ...issue.path], message: issue.code })
      }
      if (isDeathBeforeBirth(values.birthDate, values.deathDate)) {
        ctx.addIssue({
          code: 'custom',
          path: ['deathDate', 'date'],
          message: PERSON_FORM_ERROR_CODES.deathBeforeBirth,
        })
      }
    }
  })

export function emptyPersonFormValues(): PersonFormValues {
  return {
    fullName: '',
    birthName: '',
    courtesyName: '',
    posthumousName: '',
    aliasName: '',
    gender: 'unknown',
    birthDate: emptyDateGroup(),
    hasDied: false,
    deathDate: emptyDateGroup(),
    birthPlace: '',
    deathPlace: '',
    burialPlace: '',
    tombLocation: '',
    residencePlace: '',
    biography: '',
    notes: '',
  }
}

function dateToGroup(value: HistoricalDate | null): HistoricalDateFormValue {
  if (value === null) return emptyDateGroup()
  const group = emptyDateGroup()
  group.precision = value.precision
  group.display = value.display ?? ''
  group.lunar = value.lunar ?? ''
  const iso = value.date ?? ''
  switch (value.precision) {
    case 'exact':
      group.date = iso
      break
    case 'month':
      if (iso.length >= 7) {
        group.year = iso.slice(0, 4)
        group.month = String(Number(iso.slice(5, 7)))
      }
      break
    case 'year':
    case 'circa':
      if (iso.length >= 4) group.year = iso.slice(0, 4)
      break
    case 'unknown':
      break
  }
  return group
}

/** Prefills `PersonForm` in edit mode. `person.deathDate` known (any precision) ⇒ the "Đã mất" switch starts on. */
export function personToFormValues(person: Person): PersonFormValues {
  return {
    fullName: person.fullName,
    birthName: person.birthName ?? '',
    courtesyName: person.courtesyName ?? '',
    posthumousName: person.posthumousName ?? '',
    aliasName: person.aliasName ?? '',
    gender: person.gender,
    birthDate: dateToGroup(person.birthDate),
    hasDied: person.deathDate !== null,
    deathDate: dateToGroup(person.deathDate),
    birthPlace: person.birthPlace ?? '',
    deathPlace: person.deathPlace ?? '',
    burialPlace: person.burialPlace ?? '',
    tombLocation: person.tombLocation ?? '',
    residencePlace: person.residencePlace ?? '',
    biography: person.biography ?? '',
    notes: person.notes ?? '',
  }
}

interface EncodedDate {
  date: string | null
  precision: DatePrecision
  display: string | null
}

/**
 * `defaultDisplay` is supplied by the caller (`PersonForm.tsx`, from
 * `useTranslations`) rather than computed here — this module never renders a
 * user-facing string itself. `null` when the caller has no default for this
 * precision (`exact`, and `unknown` when nothing was typed), in which case an
 * empty `display` field stays empty.
 */
export function encodeDateGroup(
  group: HistoricalDateFormValue,
  defaultDisplay: string | null,
): EncodedDate {
  if (group.precision === 'exact') {
    // Ignores `defaultDisplay` on purpose: the render rule
    // (`renderHistoricalDate`) never reads `display` when precision is
    // `exact`, so a fallback here would be dead data on the wire.
    return { date: group.date || null, precision: 'exact', display: group.display.trim() || null }
  }

  const display = group.display.trim() || defaultDisplay || null
  switch (group.precision) {
    case 'year':
    case 'circa': {
      const year = group.year.trim()
      return {
        date: year ? `${year.padStart(4, '0')}-01-01` : null,
        precision: group.precision,
        display,
      }
    }
    case 'month': {
      const year = group.year.trim()
      const month = group.month.trim().padStart(2, '0')
      const date = year && month ? `${year.padStart(4, '0')}-${month}-01` : null
      return { date, precision: 'month', display }
    }
    case 'unknown':
      return { date: null, precision: 'unknown', display }
  }
}

export interface EncodeOptions {
  birthDisplay: string | null
  deathDisplay: string | null
}

/**
 * `nationality` is hardcoded `'VN'` — spec §7.7's field list
 * ("Tên gọi · Giới tính · Ngày sinh · Ngày mất · Nơi chốn · Chi/nhánh · Tiểu
 * sử · Ghi chú") names no nationality field, and `PersonCreateRequest`
 * requires the key regardless (matches the backend's own default,
 * `backend/app/schemas/person.py`'s `nationality: str = "VN"`, so a clan
 * that never touches this field gets the exact value the backend would have
 * chosen for it anyway).
 *
 * `avatar_url` is never a key on the object this returns — ADR-036 rejects
 * it outright, on every role, so this function names every field it sends
 * explicitly rather than spreading a wider object that could pick one up.
 */
export function formValuesToCreateRequest(
  values: PersonFormValues,
  options: EncodeOptions,
): PersonCreateRequest {
  const birth = encodeDateGroup(values.birthDate, options.birthDisplay)
  const death = values.hasDied
    ? encodeDateGroup(values.deathDate, options.deathDisplay)
    : { date: null, precision: 'unknown' as const, display: null }

  return {
    full_name: values.fullName.trim(),
    birth_name: values.birthName.trim() || null,
    courtesy_name: values.courtesyName.trim() || null,
    posthumous_name: values.posthumousName.trim() || null,
    alias_name: values.aliasName.trim() || null,
    gender: values.gender,
    birth_date: birth.date,
    birth_date_precision: birth.precision,
    birth_date_display: birth.display,
    death_date: death.date,
    death_date_precision: death.precision,
    death_date_display: death.display,
    lunar_birth_date: values.birthDate.lunar.trim() || null,
    lunar_death_date: values.hasDied ? values.deathDate.lunar.trim() || null : null,
    birth_place: values.birthPlace.trim() || null,
    death_place: values.deathPlace.trim() || null,
    burial_place: values.burialPlace.trim() || null,
    tomb_location: values.tombLocation.trim() || null,
    residence_place: values.residencePlace.trim() || null,
    nationality: 'VN',
    biography: values.biography.trim() || null,
    notes: values.notes.trim() || null,
  }
}

/**
 * `expected_version` (ADR-017) is supplied by the caller, never read off
 * `values` — the form has no field for it, and the whole point of §7.7c is
 * that the version to send can change out from under the form after it was
 * opened.
 *
 * **Unlike create, unchecking "Đã mất" here must send explicit `null`s, not
 * omit the keys.** `PATCH` is partial: an omitted key means "leave the
 * stored value alone" (the same convention `phone`/`email` follow,
 * `docs/contracts/rest-persons-api.md`, "a `null` clears the stored value
 * for real"). A person who record a death and then un-check the switch to
 * correct a mistake needs that death actually cleared, not silently kept
 * because this function only ever added fields.
 */
export function formValuesToUpdateRequest(
  values: PersonFormValues,
  expectedVersion: number,
  options: EncodeOptions,
): PersonUpdateRequest {
  const birth = encodeDateGroup(values.birthDate, options.birthDisplay)
  const death = values.hasDied ? encodeDateGroup(values.deathDate, options.deathDisplay) : null

  return {
    full_name: values.fullName.trim(),
    birth_name: values.birthName.trim() || null,
    courtesy_name: values.courtesyName.trim() || null,
    posthumous_name: values.posthumousName.trim() || null,
    alias_name: values.aliasName.trim() || null,
    gender: values.gender,
    birth_date: birth.date,
    birth_date_precision: birth.precision,
    birth_date_display: birth.display,
    death_date: death ? death.date : null,
    death_date_precision: death ? death.precision : 'unknown',
    death_date_display: death ? death.display : null,
    lunar_birth_date: values.birthDate.lunar.trim() || null,
    lunar_death_date: values.hasDied ? values.deathDate.lunar.trim() || null : null,
    birth_place: values.birthPlace.trim() || null,
    death_place: values.deathPlace.trim() || null,
    burial_place: values.burialPlace.trim() || null,
    tomb_location: values.tombLocation.trim() || null,
    residence_place: values.residencePlace.trim() || null,
    biography: values.biography.trim() || null,
    notes: values.notes.trim() || null,
    expected_version: expectedVersion,
  }
}
