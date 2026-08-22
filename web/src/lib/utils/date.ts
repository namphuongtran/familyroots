import { format, formatDistance } from 'date-fns'
import { vi, enUS } from 'date-fns/locale'

const LOCALE_MAP = { vi, en: enUS, zh: enUS, fr: enUS }

function getDateFnsLocale(locale = 'vi') {
  return LOCALE_MAP[locale as keyof typeof LOCALE_MAP] ?? vi
}

/** Format ISO date to a human-readable date string */
export function formatDate(isoDate: string | undefined | null, locale = 'vi'): string {
  if (!isoDate) return ''
  try {
    return format(new Date(isoDate), 'dd/MM/yyyy', {
      locale: getDateFnsLocale(locale),
    })
  } catch {
    return isoDate
  }
}

/** Format ISO date to year only */
export function formatYear(isoDate: string | undefined | null): string {
  if (!isoDate) return ''
  try {
    return new Date(isoDate).getFullYear().toString()
  } catch {
    return ''
  }
}

/**
 * Format a lifespan string for display in the family tree.
 * Returns: "1880 – 1960" or "1965 –" for living members
 * Approx dates are prefixed with "~"
 */
export function formatLifespan(
  birthDate?: string,
  deathDate?: string,
  birthApprox = false,
  deathApprox = false,
): string {
  const birth = birthDate ? `${birthApprox ? '~' : ''}${formatYear(birthDate)}` : '?'
  const death = deathDate ? `${deathApprox ? '~' : ''}${formatYear(deathDate)}` : ''

  if (!birthDate && !deathDate) return ''
  if (deathDate) return `${birth} – ${death}`
  return `${birth} –`
}

/**
 * Returns a relative time string, e.g. "7 ngày nữa"
 */
export function formatRelativeTime(isoDate: string, locale = 'vi'): string {
  try {
    return formatDistance(new Date(isoDate), new Date(), {
      addSuffix: true,
      locale: getDateFnsLocale(locale),
    })
  } catch {
    return ''
  }
}

/** Format event date, showing lunar indicator if needed */
export function formatEventDate(isoDate: string, isLunar: boolean, locale = 'vi'): string {
  const formatted = formatDate(isoDate, locale)
  return isLunar ? `${formatted} (ÂL)` : formatted
}

/** Format days_until to friendly Vietnamese string */
export function formatDaysUntil(days: number, locale = 'vi'): string {
  if (days === 0) return locale === 'vi' ? 'Hôm nay' : 'Today'
  if (days === 1) return locale === 'vi' ? 'Ngày mai' : 'Tomorrow'
  if (locale === 'vi') return `còn ${days} ngày`
  return `${days} days`
}
