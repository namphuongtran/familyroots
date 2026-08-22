/**
 * The one place that decides the fallback text `PersonForm.tsx` stores in
 * `*_date_display` when a person leaves the free-text field blank for a
 * non-exact precision — spec §7.7's own copy treats "khoảng 1750" as a
 * first-class answer, so a year/month/circa entry with nothing typed still
 * needs to read as something better than the raw stored `date` on every
 * later screen.
 *
 * Split out of `person-form-schema.ts` because that module's own header
 * comment is explicit that it "never renders a user-facing string itself" —
 * every string returned here goes through `useTranslations`, so this file is
 * the seam between the pure form schema and next-intl. `StaleWriteDialog`'s
 * diff (`stale-write-diff.ts`) calls this with the same `t` the form itself
 * uses, so the §7.7c comparison shows the same text a save would actually
 * store, not a re-derived approximation of it.
 */

import type { HistoricalDateFormValue } from './person-form-schema'

export type Translate = (key: string, values?: Record<string, string | number>) => string

export function defaultDateDisplay(t: Translate, group: HistoricalDateFormValue): string | null {
  const year = group.year.trim()
  switch (group.precision) {
    case 'year':
      return year ? t('default_display_year', { year }) : null
    case 'month': {
      const month = group.month.trim()
      return year && month ? t('default_display_month', { year, month }) : null
    }
    case 'circa':
      return year ? t('default_display_circa', { year }) : null
    case 'exact':
    case 'unknown':
      return null
  }
}
