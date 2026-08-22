'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import type { Person } from '@/domain/person/person'
import { formatHistoricalDate, isKnownDate } from './format-person-date'
import { PersonAvatar } from './PersonAvatar'

interface PersonRowProps {
  person: Person
}

/**
 * Spec §7.5's row also carries a trailing đời badge. `Person` — what
 * `GET /persons` actually returns — has no `generation` field; only
 * `PersonSearchResult` (`GET /persons/search`) does
 * (`web/src/features/persons/model/person-dto.ts`). This screen uses the
 * cursor-paginated list per the seed's own end state, so it cannot render
 * that badge honestly and does not invent one. Same story for "Chi/nhánh" —
 * no field on `Person` carries it either.
 */
export function PersonRow({ person }: PersonRowProps) {
  const locale = useLocale()
  const t = useTranslations('member')
  const unknown = t('unknown_date')

  const deceased = isKnownDate(person.deathDate)
  const birth = formatHistoricalDate(person.birthDate, locale, unknown)
  const lifespan = deceased
    ? `${birth} – ${formatHistoricalDate(person.deathDate, locale, unknown)}`
    : t('born_on', { date: birth })

  return (
    <Link
      href={`./${person.id}`}
      className="bg-card hover:bg-muted focus:ring-ring flex items-center gap-3 rounded-2xl p-3 transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
    >
      <PersonAvatar
        fullName={person.fullName}
        avatarUrl={person.avatarUrl}
        size="sm"
        isDeceased={deceased}
      />
      <div className="min-w-0 flex-1">
        <p className="text-foreground truncate text-sm font-semibold">{person.fullName}</p>
        <p className="text-muted-foreground text-xs">{lifespan}</p>
      </div>
      {deceased && (
        <span className="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-[11px]">
          {t('deceased')}
        </span>
      )}
    </Link>
  )
}
