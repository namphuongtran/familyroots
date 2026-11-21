/**
 * Presentation-only date formatting for the events screen. The recorded `HistoricalDate` goes
 * through persons' `formatHistoricalDate`, which applies the domain render rule; this file adds
 * only what that one cannot do: a backend-computed solar `YYYY-MM-DD` (`nextOccurrence`), and the
 * calendar's month, weekday and day labels, all in the reader's locale rather than date-fns' `vi`.
 */

/** `YYYY-MM-DD` for a local calendar day, the key the calendar and `nextOccurrence` share. */
export function dayKey(day: Date): string {
  const y = day.getFullYear()
  const m = String(day.getMonth() + 1).padStart(2, '0')
  const d = String(day.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * A wire calendar date in `dd/MM/yyyy` order for the locale. Pinned to UTC: `new Date('2026-12-29')`
 * is UTC midnight, and formatting in the host zone would print the 28th west of UTC.
 */
export function formatSolarDate(iso: string, locale: string): string {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

export function formatMonth(month: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(month)
}

export function formatLongDay(day: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(day)
}

/** Seven short weekday names, Sunday first, matching `Date.getDay()`. */
export function weekdayNames(locale: string): string[] {
  const format = new Intl.DateTimeFormat(locale, { weekday: 'short', timeZone: 'UTC' })
  // 2023-01-01 was a Sunday.
  return Array.from({ length: 7 }, (_, i) => format.format(new Date(Date.UTC(2023, 0, 1 + i))))
}
