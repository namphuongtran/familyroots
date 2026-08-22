import { getTranslations } from 'next-intl/server'
import { Users, GitBranch, Calendar, FileText } from 'lucide-react'
import Link from 'next/link'

export default async function DashboardPage() {
  const t = await getTranslations('dashboard')

  // ADR-055: three of these four icon tiles used to rotate through untokened
  // hues (blue, green, purple), with `events` alone already on `accent`. No
  // link is more urgent or more successful than another, so the colour was
  // decoration, not information — the same finding the stat-tile groups
  // reached. All four now share the one pair `events` already used, matching
  // `backoffice/dashboard/page.tsx`'s own icon tiles, which were uniform
  // `accent` from the start.
  const quickLinks = [
    { href: '../tree', icon: GitBranch, label: t('tree') },
    { href: '../members', icon: Users, label: t('members') },
    { href: '../events', icon: Calendar, label: t('events') },
    { href: '../documents', icon: FileText, label: t('documents') },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-foreground font-serif text-2xl">{t('welcome')}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('overview')}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {quickLinks.map(({ href, icon: Icon, label }) => (
          <Link
            key={href}
            href={href}
            className="border-border bg-card hover:border-input flex flex-col items-center gap-2 rounded-2xl border p-4 shadow-xs transition-all hover:shadow-md"
          >
            <div className="bg-accent text-accent-foreground rounded-xl p-3">
              <Icon className="h-5 w-5" />
            </div>
            <span className="text-foreground text-xs font-medium">{label}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
