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
        <h1 className="text-2xl font-bold text-gray-900">{t('dashboard_title')}</h1>
        <p className="mt-1 text-sm text-gray-500">{t('dashboard_subtitle')}</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {mockStats.map((stat) => {
          const Icon = stat.icon
          return (
            <div
              key={stat.label}
              className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xs"
            >
              <div className="p-5">
                <div className="flex items-center gap-4">
                  <div className="rounded-lg bg-amber-50 p-3">
                    <Icon className="h-5 w-5 text-amber-700" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-gray-500">{stat.label}</p>
                    <p className="mt-0.5 text-2xl font-semibold text-gray-900">{stat.value}</p>
                  </div>
                </div>
                <p
                  className={`mt-3 text-xs ${stat.positive ? 'text-green-600' : 'text-orange-600'}`}
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
        <h2 className="mb-4 text-lg font-semibold text-gray-900">{t('quick_actions')}</h2>
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
      className="relative flex flex-col rounded-xl border border-gray-200 bg-white p-5 shadow-xs transition-all hover:border-amber-400 hover:shadow-sm"
    >
      {badge && (
        <span className="absolute top-4 right-4 flex h-5 w-5 items-center justify-center rounded-full bg-orange-500 text-xs font-medium text-white">
          {badge}
        </span>
      )}
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      <p className="mt-1 text-xs text-gray-500">{description}</p>
    </a>
  )
}
