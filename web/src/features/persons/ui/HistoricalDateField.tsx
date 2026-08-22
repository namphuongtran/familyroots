'use client'

/**
 * One `HistoricalDate` group (spec §7.7's `HistoricalDateField`), covering
 * all five ADR-011 precisions plus the ADR-018 lunar display string.
 *
 * A `Controller`-free design: every sub-field is a plain registered input,
 * and only which sub-fields are *shown* depends on the selected precision —
 * `useWatch` reads that one value to decide the layout, the same value RHF
 * already tracks for validation. Lives in `ui/` and reads `useFormContext`
 * rather than taking `register`/`watch` as props, so `PersonForm.tsx` does
 * not have to thread them through two levels for what is really one form.
 */

import { useFormContext, useWatch } from 'react-hook-form'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils/cn'
import type { DatePrecision } from '@/domain/date/historical-date'
import { PERSON_FORM_ERROR_CODES, type PersonFormValues } from './person-form-schema'

const PRECISIONS: readonly DatePrecision[] = ['exact', 'year', 'month', 'circa', 'unknown']

interface HistoricalDateFieldProps {
  /** Which group this instance edits — the two the form has. */
  namePrefix: 'birthDate' | 'deathDate'
  idBase: string
}

const inputClass =
  'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'

/** Every zod issue code this field can show, mapped through `useTranslations('member_form')`. */
function errorText(t: (key: string) => string, code: string | undefined): string | null {
  if (!code) return null
  switch (code) {
    case PERSON_FORM_ERROR_CODES.exactDateRequired:
      return t('error_exact_date_required')
    case PERSON_FORM_ERROR_CODES.yearRequired:
      return t('error_year_required')
    case PERSON_FORM_ERROR_CODES.monthRequired:
      return t('error_month_required')
    case PERSON_FORM_ERROR_CODES.yearOutOfRange:
      return t('error_year_out_of_range')
    case PERSON_FORM_ERROR_CODES.deathBeforeBirth:
      return t('error_death_before_birth')
    default:
      return null
  }
}

export function HistoricalDateField({ namePrefix, idBase }: HistoricalDateFieldProps) {
  const t = useTranslations('member_form')
  const {
    register,
    control,
    formState: { errors },
  } = useFormContext<PersonFormValues>()

  const precision = useWatch({ control, name: `${namePrefix}.precision` })
  const group = errors[namePrefix]

  return (
    <div className="space-y-2">
      <div>
        <label
          htmlFor={`${idBase}-precision`}
          className="text-foreground mb-1 block text-sm font-medium"
        >
          {t('precision_label')}
        </label>
        <select
          id={`${idBase}-precision`}
          {...register(`${namePrefix}.precision`)}
          className={cn(inputClass, 'appearance-none')}
        >
          {PRECISIONS.map((value) => (
            <option key={value} value={value}>
              {t(`precision_${value}`)}
            </option>
          ))}
        </select>
        <p className="text-muted-foreground mt-1 text-xs">{t('precision_helper')}</p>
      </div>

      {precision === 'exact' && (
        <div>
          <label
            htmlFor={`${idBase}-date`}
            className="text-foreground mb-1 block text-sm font-medium"
          >
            {t('date_label')}
          </label>
          <input
            id={`${idBase}-date`}
            type="date"
            {...register(`${namePrefix}.date`)}
            aria-invalid={group?.date ? true : undefined}
            className={inputClass}
          />
          {errorText(t, group?.date?.message) && (
            <p className="text-destructive mt-1 text-xs">{errorText(t, group?.date?.message)}</p>
          )}
        </div>
      )}

      {(precision === 'year' || precision === 'circa' || precision === 'month') && (
        <div className="flex gap-3">
          <div className="flex-1">
            <label
              htmlFor={`${idBase}-year`}
              className="text-foreground mb-1 block text-sm font-medium"
            >
              {t('year_label')}
            </label>
            <input
              id={`${idBase}-year`}
              type="text"
              inputMode="numeric"
              placeholder="1750"
              {...register(`${namePrefix}.year`)}
              aria-invalid={group?.year ? true : undefined}
              className={inputClass}
            />
            {errorText(t, group?.year?.message) && (
              <p className="text-destructive mt-1 text-xs">{errorText(t, group?.year?.message)}</p>
            )}
          </div>
          {precision === 'month' && (
            <div className="flex-1">
              <label
                htmlFor={`${idBase}-month`}
                className="text-foreground mb-1 block text-sm font-medium"
              >
                {t('month_label')}
              </label>
              <input
                id={`${idBase}-month`}
                type="text"
                inputMode="numeric"
                placeholder="3"
                {...register(`${namePrefix}.month`)}
                aria-invalid={group?.month ? true : undefined}
                className={inputClass}
              />
              {errorText(t, group?.month?.message) && (
                <p className="text-destructive mt-1 text-xs">
                  {errorText(t, group?.month?.message)}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {precision !== 'exact' && (
        <div>
          <label
            htmlFor={`${idBase}-display`}
            className="text-foreground mb-1 block text-sm font-medium"
          >
            {t('display_label')}
          </label>
          <input
            id={`${idBase}-display`}
            type="text"
            placeholder={t('display_placeholder')}
            {...register(`${namePrefix}.display`)}
            className={inputClass}
          />
        </div>
      )}

      <div>
        <label
          htmlFor={`${idBase}-lunar`}
          className="text-foreground mb-1 block text-sm font-medium"
        >
          {t('lunar_label')}
        </label>
        <input
          id={`${idBase}-lunar`}
          type="text"
          placeholder={t('lunar_placeholder')}
          {...register(`${namePrefix}.lunar`)}
          className={inputClass}
        />
      </div>
    </div>
  )
}
