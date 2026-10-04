'use client'

import Link from 'next/link'
import { X, Edit, Users } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import {
  PersonAvatar,
  formatHistoricalDate,
  isKnownDate,
  usePerson,
  type Person,
} from '@/features/persons'
import { useClientRequestContext } from '@/shared/http/context.client'

interface MemberSidebarProps {
  personId: string
  onClose: () => void
}

/**
 * "1900 – 1975", "1900 –" while no death date is known, and nothing when
 * neither date is. Each side goes through persons' `formatHistoricalDate`, so
 * a `year` or `circa` date prints its `display` and an `exact` one its `date`.
 */
function lifespan(person: Person, locale: string): string {
  const birthKnown = isKnownDate(person.birthDate)
  const deathKnown = isKnownDate(person.deathDate)
  if (!birthKnown && !deathKnown) return ''
  const birth = formatHistoricalDate(person.birthDate, locale, '?')
  if (!deathKnown) return `${birth} –`
  return `${birth} – ${formatHistoricalDate(person.deathDate, locale, '?')}`
}

/**
 * Reads `GET /persons/{id}`, whose `PersonResponse` carries no generation, so
 * this sidebar shows none. Đời comes from the tree's own read model, and
 * showing it here is the tree slice's call.
 */
export function MemberSidebar({ personId, onClose }: MemberSidebarProps) {
  const t = useTranslations('tree')
  const locale = useLocale()
  const { context, ready, refreshAuth } = useClientRequestContext()
  const { data: person, isPending } = usePerson(
    personId,
    {},
    { context, refreshAuth, enabled: ready },
  )

  return (
    <div className="border-border bg-card absolute top-4 left-4 z-20 w-64 overflow-hidden rounded-xl border shadow-lg">
      {/* Header */}
      <div className="border-border flex items-center justify-between border-b px-3 py-2">
        <span className="text-foreground text-sm font-semibold">{t('details')}</span>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {!ready || isPending ? (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-12 w-12 shrink-0 rounded-full" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
      ) : person ? (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <PersonAvatar
              avatarUrl={person.avatarUrl}
              fullName={person.fullName}
              size="sm"
              isDeceased={isKnownDate(person.deathDate)}
            />
            <div>
              <p className="text-foreground text-sm font-semibold">{person.fullName}</p>
              <p className="text-muted-foreground text-xs">{lifespan(person, locale)}</p>
            </div>
          </div>

          {person.birthPlace && (
            <div className="text-muted-foreground text-xs">
              <span className="font-medium">{t('born_in')}: </span>
              {person.birthPlace}
            </div>
          )}

          {person.notes && (
            <p className="text-muted-foreground line-clamp-3 text-xs italic">{person.notes}</p>
          )}

          <div className="flex gap-2 pt-1">
            <Link
              href={`/persons/${person.id}`}
              className="bg-primary-container text-primary-container-foreground hover:bg-primary-container-hover flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs transition-colors"
            >
              <Users className="h-3 w-3" />
              {t('view_profile')}
            </Link>
            <Link
              href={`/persons/${person.id}/edit`}
              className="border-border text-muted-foreground hover:bg-muted flex flex-1 items-center justify-center gap-1 rounded-md border px-2 py-1.5 text-xs transition-colors"
            >
              <Edit className="h-3 w-3" />
              {t('edit')}
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  )
}
