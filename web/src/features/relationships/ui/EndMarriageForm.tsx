'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import type { DatePrecision } from '@/domain/date/historical-date'
import {
  dateGroupIssues,
  defaultDateDisplay,
  emptyDateGroup,
  encodeDateGroup,
  PERSON_FORM_ERROR_CODES,
  type HistoricalDateFormValue,
} from '@/features/persons'
import { fieldClass, primaryButtonClass, quietButtonClass } from './editor-classes'

const PRECISIONS: readonly DatePrecision[] = ['exact', 'year', 'month', 'circa', 'unknown']

export type EndStatus = 'divorced' | 'widowed'

/** The fields an end-of-marriage PATCH carries, before `expected_version` is added. */
export interface EndMarriageFields {
  status: EndStatus
  divorce_date: string | null
  divorce_date_precision: DatePrecision
  divorce_date_display: string | null
}

interface EndMarriageFormProps {
  readonly idBase: string
  readonly saving: boolean
  readonly error: string | null
  readonly onSubmit: (fields: EndMarriageFields) => void
  readonly onCancel: () => void
}

/**
 * Ends a marriage as divorced or widowed, with the end date entered as a `HistoricalDate`
 * (ADR-011's five precisions). The wire has one end-date field, `divorce_date`, for both
 * statuses. The date group reuses the persons form's encoding (`encodeDateGroup`,
 * `defaultDateDisplay`) and its validation (`dateGroupIssues`), so an end date is stored and
 * checked the way a death date is. The wire carries no lunar field for it, so none is offered.
 */
export function EndMarriageForm({
  idBase,
  saving,
  error,
  onSubmit,
  onCancel,
}: EndMarriageFormProps) {
  const t = useTranslations('relationship_editor')
  const tForm = useTranslations('member_form')
  const [status, setStatus] = useState<EndStatus>('divorced')
  const [group, setGroup] = useState<HistoricalDateFormValue>(emptyDateGroup)
  const [issues, setIssues] = useState<Record<string, string>>({})

  function set<K extends keyof HistoricalDateFormValue>(key: K, value: HistoricalDateFormValue[K]) {
    setGroup((g) => ({ ...g, [key]: value }))
  }

  function issueText(field: string): string | null {
    const code = issues[field]
    switch (code) {
      case PERSON_FORM_ERROR_CODES.exactDateRequired:
        return tForm('error_exact_date_required')
      case PERSON_FORM_ERROR_CODES.yearRequired:
        return tForm('error_year_required')
      case PERSON_FORM_ERROR_CODES.monthRequired:
        return tForm('error_month_required')
      case PERSON_FORM_ERROR_CODES.yearOutOfRange:
        return tForm('error_year_out_of_range')
      default:
        return null
    }
  }

  function submit() {
    const found: Record<string, string> = {}
    for (const issue of dateGroupIssues(group)) found[issue.path[0]] = issue.code
    setIssues(found)
    if (Object.keys(found).length > 0) return
    const encoded = encodeDateGroup(group, defaultDateDisplay(tForm, group))
    onSubmit({
      status,
      divorce_date: encoded.date,
      divorce_date_precision: encoded.precision,
      divorce_date_display: encoded.display,
    })
  }

  const p = group.precision

  return (
    <div className="bg-muted space-y-3 rounded-xl p-3">
      <fieldset>
        <legend className="text-foreground mb-1 text-sm font-medium">{t('end_reason')}</legend>
        <div className="flex flex-wrap gap-2">
          {(['divorced', 'widowed'] as const).map((value) => (
            <label
              key={value}
              className="border-input has-[:checked]:bg-primary has-[:checked]:text-primary-foreground has-[:checked]:border-primary text-foreground flex cursor-pointer items-center rounded-full border px-4 py-2 text-sm"
            >
              <input
                type="radio"
                name={`${idBase}-status`}
                value={value}
                checked={status === value}
                onChange={() => setStatus(value)}
                className="sr-only"
              />
              {t(`end_${value}`)}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor={`${idBase}-precision`} className="text-foreground mb-1 block text-sm">
          {t('end_date')} · {tForm('precision_label')}
        </label>
        <select
          id={`${idBase}-precision`}
          value={p}
          onChange={(e) => set('precision', e.target.value as DatePrecision)}
          className={fieldClass}
        >
          {PRECISIONS.map((value) => (
            <option key={value} value={value}>
              {tForm(`precision_${value}`)}
            </option>
          ))}
        </select>
      </div>

      {p === 'exact' && (
        <div>
          <label htmlFor={`${idBase}-date`} className="text-foreground mb-1 block text-sm">
            {tForm('date_label')}
          </label>
          <input
            id={`${idBase}-date`}
            type="date"
            value={group.date}
            aria-invalid={issues.date ? true : undefined}
            onChange={(e) => set('date', e.target.value)}
            className={fieldClass}
          />
          {issueText('date') && (
            <p className="text-destructive mt-1 text-xs">{issueText('date')}</p>
          )}
        </div>
      )}

      {(p === 'year' || p === 'month' || p === 'circa') && (
        <div className="flex flex-wrap gap-3">
          <div className="min-w-0 flex-1 basis-24">
            <label htmlFor={`${idBase}-year`} className="text-foreground mb-1 block text-sm">
              {tForm('year_label')}
            </label>
            <input
              id={`${idBase}-year`}
              type="text"
              inputMode="numeric"
              value={group.year}
              aria-invalid={issues.year ? true : undefined}
              onChange={(e) => set('year', e.target.value)}
              className={fieldClass}
            />
            {issueText('year') && (
              <p className="text-destructive mt-1 text-xs">{issueText('year')}</p>
            )}
          </div>
          {p === 'month' && (
            <div className="min-w-0 flex-1 basis-24">
              <label htmlFor={`${idBase}-month`} className="text-foreground mb-1 block text-sm">
                {tForm('month_label')}
              </label>
              <input
                id={`${idBase}-month`}
                type="text"
                inputMode="numeric"
                value={group.month}
                aria-invalid={issues.month ? true : undefined}
                onChange={(e) => set('month', e.target.value)}
                className={fieldClass}
              />
              {issueText('month') && (
                <p className="text-destructive mt-1 text-xs">{issueText('month')}</p>
              )}
            </div>
          )}
        </div>
      )}

      {p !== 'exact' && (
        <div>
          <label htmlFor={`${idBase}-display`} className="text-foreground mb-1 block text-sm">
            {tForm('display_label')}
          </label>
          <input
            id={`${idBase}-display`}
            type="text"
            value={group.display}
            placeholder={tForm('display_placeholder')}
            onChange={(e) => set('display', e.target.value)}
            className={fieldClass}
          />
        </div>
      )}

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={onCancel} disabled={saving} className={quietButtonClass}>
          {t('cancel')}
        </button>
        <button type="button" onClick={submit} disabled={saving} className={primaryButtonClass}>
          {saving ? t('saving') : t('end_marriage_save')}
        </button>
      </div>
    </div>
  )
}
