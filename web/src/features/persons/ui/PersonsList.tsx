'use client'

import { useTranslations } from 'next-intl'
import { ApiError } from '@/shared/http/errors'
import { usePersonsList } from '../hooks/use-persons-queries'
import { PersonRow } from './PersonRow'
import { PersonsErrorState } from './PersonsErrorState'
import { PersonsListSkeleton } from './PersonsListSkeleton'
import { usePersonsRequestContext } from './use-persons-request-context'

/** `message` is only ever shown, never branched on — `ApiError.message` arrives already localized from the backend (`web/CLAUDE.md`, "The spine"). */
function errorMessage(error: unknown): string | null {
  return error instanceof ApiError ? error.message : null
}

/**
 * The cursor-paginated persons list (spec §7.5), a Client Component because
 * pagination is inherently interactive state. The page shell around this
 * (title, the role-gated "add" link) stays a Server Component — see
 * `app/[locale]/(dashboard)/members/page.tsx`.
 *
 * Pagination is the explicit "Tải thêm" button only, on purpose: spec §7.5
 * reserves auto-load-on-scroll for the mobile client and says infinite
 * scroll on desktop "breaks keyboard users and hides the page footer"
 * (`T-07`). `usePersonsList`'s own cursor rule (S-030) means this component
 * never sees a cursor at all — it only ever calls `fetchNextPage()`.
 */
export function PersonsList() {
  const t = useTranslations('members')
  const { context, ready } = usePersonsRequestContext()
  const {
    data,
    isPending,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
  } = usePersonsList({}, { context, enabled: ready })

  if (!ready || isPending) {
    return <PersonsListSkeleton rows={8} />
  }

  /**
   * Checked on `data`, not on `isError`. TanStack Query's `isError` reflects
   * the *last* fetch attempt for this query, so a failed `fetchNextPage()`
   * sets it too, even though page one's rows are still sitting in `data` —
   * confirmed empirically in `PersonsList.test.tsx`'s "keeps the
   * already-loaded rows visible" case, which this exact `if (isError)`
   * ordering used to fail by discarding those rows for a load-more error.
   * `data === undefined` is the one condition that is true only when no
   * page has ever loaded, which is the only time a full-screen error state
   * is honest — spec §7.5: "already-loaded pages remain visible above it."
   */
  if (data === undefined) {
    return (
      <PersonsErrorState
        title={t('error_title')}
        message={errorMessage(error)}
        onRetry={() => refetch()}
      />
    )
  }

  const persons = data.pages.flatMap((page) => page.items)

  if (persons.length === 0) {
    return <p className="text-muted-foreground py-12 text-center text-sm">{t('no_members')}</p>
  }

  return (
    <div>
      <ul className="space-y-2">
        {persons.map((person) => (
          <li key={person.id}>
            <PersonRow person={person} />
          </li>
        ))}
      </ul>

      {isFetchingNextPage && <PersonsListSkeleton rows={2} className="mt-2" />}

      <div className="mt-4 flex flex-col items-center gap-2">
        {isFetchNextPageError && <p className="text-destructive text-sm">{t('load_more_error')}</p>}
        {hasNextPage ? (
          <button
            type="button"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-5 py-2 text-sm font-medium transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none disabled:opacity-60"
          >
            {isFetchingNextPage ? t('loading_more') : t('load_more')}
          </button>
        ) : (
          <p className="text-muted-foreground text-sm">
            {t('all_shown', { count: persons.length })}
          </p>
        )}
      </div>
    </div>
  )
}
