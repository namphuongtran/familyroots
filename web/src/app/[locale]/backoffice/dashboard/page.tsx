import { getTranslations } from 'next-intl/server'
import { Users, Clock, FileText, TrendingUp } from 'lucide-react'

/**
 * Backoffice dashboard — landing page for clan admins.
 *
 * Stats are intentionally static/mock for now. Wire up real Supabase queries
 * once the `clan_id` is available from the session via `getClanId()` helper.
 */
export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: 'Backoffice' })
  return { title: t('dashboard_title') }
}

/**
 * Each label is a full key path, because three of the four reuse a key that already says the same
 * thing in all four locales (#197): the platform metrics' `Total Members`, the admin users page's
 * `Pending Approval`, and the clan dashboard's `Documents`. Only `Tree Completeness` is new.
 *
 * Not copy: every `value` and `change` here is mock data, not words anyone wrote for a reader.
 * They leave when the stats are wired, so they are not translated.
 */
const mockStats = [
  {
    labelKey: 'platform.total_members',
    value: '248',
    icon: Users,
    change: '+12 this month',
    positive: true,
  },
  {
    labelKey: 'admin.pending_approval',
    value: '7',
    icon: Clock,
    change: '3 new today',
    positive: false,
  },
  {
    labelKey: 'dashboard.documents',
    value: '134',
    icon: FileText,
    change: '+5 this week',
    positive: true,
  },
  {
    labelKey: 'Backoffice.stat_tree_completeness',
    value: '73%',
    icon: TrendingUp,
    change: '+2% since last month',
    positive: true,
  },
] as const

export default async function BackofficeDashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: 'Backoffice' })
  const tAll = await getTranslations({ locale })

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

      {/* Stats grid */}
      <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {mockStats.map((stat) => {
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
                    <p className="text-foreground mt-0.5 text-2xl font-semibold">{stat.value}</p>
                  </div>
                </div>
                {/*
                  ADR-055: was `text-green-600` / `text-orange-600`, neither
                  tokened. The trend direction is genuine information (a real
                  positive/negative reading, once this stops being mock data)
                  and the change text itself already says which — "+12 this
                  month" versus "3 new today" — so colour reinforces rather
                  than carries it alone. `success` is new (spec § 2.1/2.2);
                  `destructive` was already gated.
                */}
                <p
                  className={`mt-3 text-xs ${stat.positive ? 'text-success' : 'text-destructive'}`}
                >
                  {stat.change}
                </p>
              </div>
            </li>
          )
        })}
      </ul>

      {/* Quick actions */}
      <div className="mt-8">
        <h2 className="text-foreground mb-4 text-lg font-semibold">{t('quick_actions')}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            href={`/${locale}/backoffice/persons`}
            title={t('action_add_member')}
            description={t('action_add_member_desc')}
          />
          <QuickAction
            href={`/${locale}/backoffice/approvals`}
            title={t('action_review_approvals')}
            description={t('action_review_approvals_desc')}
            badge="7"
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
        */}
        {badge && (
          <span className="bg-destructive text-destructive-foreground ml-auto flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-medium">
            {badge}
          </span>
        )}
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{description}</p>
    </a>
  )
}
