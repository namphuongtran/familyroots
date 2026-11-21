'use client'

import Link from 'next/link'
import { Users, X } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { PersonAvatar, isKnownDate } from '@/features/persons'
import { useClientRequestContext } from '@/shared/http/context.client'
import { useTreeFocus } from '../hooks/use-tree-queries'
import { GenerationBadge } from './GenerationBadge'
import { WifeGroups } from './WifeGroups'

/** One generation below the focus is all the panel draws: its children, grouped by wife. */
const FOCUS_QUERY = { descendants: 1 } as const

/**
 * The selected person's focus view, `GET /tree/focus/{person_id}`: the ancestor breadcrumb, the
 * person with their đời badge, and their children grouped by wife (spec § 3.3, § 7.4a). Every
 * ancestor and child re-focuses the panel.
 */
export function FocusPanel({
  personId,
  onSelectPerson,
  onClose,
}: {
  personId: string
  onSelectPerson: (personId: string) => void
  onClose: () => void
}) {
  const t = useTranslations('tree')
  const locale = useLocale()
  const { context, ready, refreshAuth } = useClientRequestContext()
  const { data, isPending, isError, refetch } = useTreeFocus(personId, FOCUS_QUERY, {
    context,
    refreshAuth,
    enabled: ready,
  })
  const person = data?.subtree ?? null

  return (
    <aside
      aria-label={t('details')}
      className="border-border bg-card absolute top-14 left-4 z-20 max-h-[calc(100%-4rem)] w-72 overflow-y-auto rounded-xl border shadow-lg"
    >
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-foreground text-sm font-semibold">{t('details')}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('close')}
          className="text-muted-foreground hover:text-foreground focus:ring-ring rounded-md transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {!ready || isPending ? (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
            <Skeleton className="h-4 w-28" />
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
      ) : isError ? (
        <div className="space-y-2 p-4">
          <p className="text-muted-foreground text-xs">{t('load_error')}</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="text-primary text-xs font-medium hover:underline"
          >
            {t('retry')}
          </button>
        </div>
      ) : person ? (
        <div className="space-y-4 p-4 pt-0">
          {data && data.ancestors.length > 0 && (
            <nav aria-label={t('ancestors')}>
              <ol className="flex flex-wrap items-center gap-1 text-[11px]">
                {data.ancestors.map((ancestor) => (
                  <li key={ancestor.id} className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onSelectPerson(ancestor.id)}
                      className="bg-muted text-muted-foreground hover:text-foreground rounded-full px-2 py-0.5"
                    >
                      {ancestor.fullName}
                    </button>
                    <span aria-hidden="true" className="text-muted-foreground">
                      ›
                    </span>
                  </li>
                ))}
              </ol>
            </nav>
          )}

          <div className="flex items-center gap-3">
            <PersonAvatar
              avatarUrl={person.avatarUrl}
              fullName={person.fullName}
              size="sm"
              isDeceased={isKnownDate(person.deathDate)}
            />
            <div className="min-w-0 space-y-1">
              <h2 className="text-foreground text-sm font-semibold">{person.fullName}</h2>
              <GenerationBadge generation={person.generation} explainable />
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="text-muted-foreground text-xs font-medium">{t('children')}</h3>
            <WifeGroups parent={person} onSelectPerson={onSelectPerson} />
          </div>

          <Link
            href={`/${locale}/members/${person.id}`}
            className="bg-primary-container text-primary-container-foreground hover:bg-primary-container-hover flex items-center justify-center gap-1 rounded-full px-2 py-1.5 text-xs transition-colors"
          >
            <Users className="h-3 w-3" />
            {t('view_profile')}
          </Link>
        </div>
      ) : null}
    </aside>
  )
}
