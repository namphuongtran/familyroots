'use client'

import type { ComponentType } from 'react'
import { useTranslations } from 'next-intl'
import { Clock, FileText, TrendingUp, Users } from 'lucide-react'
import { useClanStats } from '@/features/admin'
import { useClientRequestContext } from '@/shared/http/context.client'

/**
 * What a stat tile shows. `count` is a number an endpoint returned. `not-counted` is a stat no
 * endpoint backs yet, and it says so in words: the tile never shows an invented number (#314).
 */
type StatReading =
  | { kind: 'count'; value: number }
  | { kind: 'loading' }
  | { kind: 'unavailable' }
  | { kind: 'not-counted' }

interface Stat {
  /** A full key path; three of the four reuse a key that already says the same thing (#197). */
  labelKey: string
  icon: ComponentType<{ className?: string }>
  reading: StatReading
}

/**
 * The backoffice landing page for a clan admin. The two counts come from
 * `GET /clans/me?include=stats`, the one read that returns exact clan totals: `total_members`
 * (persons in the tree) and `pending_users` (accounts waiting for approval). The approvals badge
 * reads the same `pending_users`, so the badge and the tile cannot disagree.
 *
 * Two tiles have no backing count. No endpoint returns a clan's document total (`GET /documents`
 * is cursor-paginated, and a page size is not a total), and tree completeness has no metric at all,
 * which #314 leaves out of scope. Both render `Backoffice.stat_not_counted`.
 *
 * The trend lines under each tile ("+12 this month") were mock data with nothing behind them, so
 * they are gone, not wired.
 */
export function BackofficeDashboard({ locale }: { locale: string }) {
  const t = useTranslations('Backoffice')
  const tAll = useTranslations()
  const request = useClientRequestContext()
  const stats = useClanStats({
    context: request.context,
    refreshAuth: request.refreshAuth,
    enabled: request.ready,
  })

  const counted = (value: (s: NonNullable<typeof stats.data>) => number): StatReading => {
    if (stats.data) return { kind: 'count', value: value(stats.data) }
    if (stats.isError) return { kind: 'unavailable' }
    return { kind: 'loading' }
  }

  const tiles: Stat[] = [
    {
      labelKey: 'platform.total_members',
      icon: Users,
      reading: counted((s) => s.totalMembers),
    },
    {
      labelKey: 'admin.pending_approval',
      icon: Clock,
      reading: counted((s) => s.pendingUsers),
    },
    { labelKey: 'dashboard.documents', icon: FileText, reading: { kind: 'not-counted' } },
    {
      labelKey: 'Backoffice.stat_tree_completeness',
      icon: TrendingUp,
      reading: { kind: 'not-counted' },
    },
  ]

  const pending = stats.data?.pendingUsers

  // #175: `px-4` below `sm`, not `p-8`, because T-04 needs the room. At 320 px and a 32px root
  // a stacked stat card's text column is 110 px under `p-8` and 158 px under spec § 2.4's
  // `space-5`, and the widest unbreakable label word, English's `Completeness`, is 164 px. `px-4`
  // gives 174.
  return (
    <div className="px-4 py-8 sm:px-8">
      {/* Header */}
      <div className="mb-8">
        {/*
          #236: `wrap-break-word`, because English's `Dashboard` is one word of 258 px at
          320 px and 200% text, in this column's 256. It breaks inside a word only where that
          word cannot fit, so it reads `Dashboar` then `d` there and changes nothing wherever
          every word fits. The size stays: spec § 2.3 puts a page title at `display-md`,
          larger still, and that is spec § 7's redesign.
        */}
        <h1 className="text-foreground text-2xl font-bold wrap-break-word">
          {t('dashboard_title')}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('dashboard_subtitle')}</p>
      </div>

      {/*
        Stats grid. #212: the text size sets the column count, not the viewport. The
        `sm:grid-cols-2 lg:grid-cols-4` this replaces kept four columns at 1024 px and 200% text,
        where the `lg` rail leaves `main` 496 px, so every stat line was 0 px wide. Each track is
        at least 12.5rem, so it doubles with the text. `min(…, 100%)` keeps a track no wider
        than the grid, or a 400 px minimum scrolls the page at 320 px. `auto-fit`, not
        `auto-fill`, so four cards on one row take the whole row rather than leave a fifth,
        empty track at 1440 px.
      */}
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(min(12.5rem,100%),1fr))] gap-5">
        {tiles.map((stat) => {
          const Icon = stat.icon
          return (
            <li
              key={stat.labelKey}
              className="border-border bg-card overflow-hidden rounded-xl border shadow-xs"
            >
              <div className="p-5">
                {/*
                  #175: the text sits beside the icon only while its column keeps
                  `basis-24`, 6rem, which clears the widest label word (English's
                  `Completeness`, 5.1rem). Below that it wraps under the icon. Beside it at
                  320 px and 200% text, the column was 0 px wide and every value was clipped.
                */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  <div className="bg-accent rounded-lg p-3">
                    <Icon className="text-accent-foreground h-5 w-5" />
                  </div>
                  <div className="min-w-0 grow basis-24">
                    <p className="text-muted-foreground text-xs font-medium">
                      {tAll(stat.labelKey)}
                    </p>
                    <StatValue reading={stat.reading} />
                  </div>
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      {/* Quick actions */}
      <div className="mt-8">
        <h2 className="text-foreground mb-4 text-lg font-semibold">{t('quick_actions')}</h2>
        {/* #212: the stats grid's pattern, over a 15rem track for the longer titles. */}
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(15rem,100%),1fr))] gap-4">
          <QuickAction
            href={`/${locale}/backoffice/persons`}
            title={t('action_add_member')}
            description={t('action_add_member_desc')}
          />
          <QuickAction
            href={`/${locale}/backoffice/approvals`}
            title={t('action_review_approvals')}
            description={t('action_review_approvals_desc')}
            badge={pending ? String(pending) : undefined}
          />
          <QuickAction
            href={`/${locale}/backoffice/tree`}
            title={t('action_manage_tree')}
            description={t('action_manage_tree_desc')}
          />
        </div>
      </div>
    </div>
  )
}

function StatValue({ reading }: { reading: StatReading }) {
  const t = useTranslations('Backoffice')
  switch (reading.kind) {
    case 'count':
      return <p className="text-foreground mt-0.5 text-2xl font-semibold">{reading.value}</p>
    case 'loading':
      return (
        <p className="text-muted-foreground mt-0.5 text-2xl font-semibold" aria-busy="true">
          —
        </p>
      )
    case 'unavailable':
      return <p className="text-muted-foreground mt-1.5 text-sm">{t('stat_unavailable')}</p>
    case 'not-counted':
      return <p className="text-muted-foreground mt-1.5 text-sm">{t('stat_not_counted')}</p>
  }
}

function QuickAction({
  href,
  title,
  description,
  badge,
}: {
  href: string
  title: string
  description: string
  badge?: string
}) {
  return (
    <a
      href={href}
      className="border-border bg-card hover:border-accent-foreground/40 flex flex-col rounded-xl border p-5 shadow-xs transition-all hover:shadow-sm"
    >
      {/*
        #175: the badge shares the title's line only while the title fits on one line
        beside it. Otherwise `flex-wrap-reverse` lifts it onto a line of its own above,
        and the title gets the card's whole width. It was `absolute top-4 right-4`, which
        at 320 px and 200% text sat on the title. Reserving its room beside the title
        was not enough either: the title kept 110 px, and English's `approvals` is 134.
      */}
      <div className="flex flex-wrap-reverse items-center gap-x-3 gap-y-2">
        <h3 className="text-foreground min-w-0 grow text-sm font-semibold">{title}</h3>
        {/*
          ADR-055: was `bg-orange-500 text-white`, untokened. A count badge on
          a pending-approval action is the same "needs attention" reading
          `destructive` already carries elsewhere in this codebase (the reject
          button, the admin role state) — reused rather than adding a solid
          warning-fill token nothing else needs yet.

          #314: the count is `stats.pending_users`, and there is no badge while it loads, when it
          fails, or when nobody is waiting.
        */}
        {badge && (
          <span
            data-testid="approvals-badge"
            className="bg-destructive text-destructive-foreground ml-auto flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1 text-xs font-medium"
          >
            {badge}
          </span>
        )}
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{description}</p>
    </a>
  )
}
