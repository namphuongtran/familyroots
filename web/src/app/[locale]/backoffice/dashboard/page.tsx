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

const mockStats = [
  {
    label: 'Total Members',
    value: '248',
    icon: Users,
    change: '+12 this month',
    positive: true,
  },
  {
    label: 'Pending Approvals',
    value: '7',
    icon: Clock,
    change: '3 new today',
    positive: false,
  },
  {
    label: 'Documents',
    value: '134',
    icon: FileText,
    change: '+5 this week',
    positive: true,
  },
  {
    label: 'Tree Completeness',
    value: '73%',
    icon: TrendingUp,
    change: '+2% since last month',
    positive: true,
  },
]

export default async function BackofficeDashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: 'Backoffice' })

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-foreground text-2xl font-bold">{t('dashboard_title')}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('dashboard_subtitle')}</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {mockStats.map((stat) => {
          const Icon = stat.icon
          return (
            <div
              key={stat.label}
              className="border-border bg-card overflow-hidden rounded-xl border shadow-xs"
            >
              <div className="p-5">
                <div className="flex items-center gap-4">
                  <div className="bg-accent rounded-lg p-3">
                    <Icon className="text-accent-foreground h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-muted-foreground truncate text-xs font-medium">
                      {stat.label}
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
            </div>
          )
        })}
      </div>

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
      className="border-border bg-card hover:border-accent-foreground/40 relative flex flex-col rounded-xl border p-5 shadow-xs transition-all hover:shadow-sm"
    >
      {/*
        ADR-055: was `bg-orange-500 text-white`, untokened. A count badge on
        a pending-approval action is the same "needs attention" reading
        `destructive` already carries elsewhere in this codebase (the reject
        button, the admin role state) — reused rather than adding a solid
        warning-fill token nothing else needs yet.
      */}
      {badge && (
        <span className="bg-destructive text-destructive-foreground absolute top-4 right-4 flex h-5 w-5 items-center justify-center rounded-full text-xs font-medium">
          {badge}
        </span>
      )}
      <h3 className="text-foreground text-sm font-semibold">{title}</h3>
      <p className="text-muted-foreground mt-1 text-xs">{description}</p>
    </a>
  )
}
