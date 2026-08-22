import { getTranslations } from 'next-intl/server'
import { Users, GitBranch, Calendar, FileText } from 'lucide-react'
import Link from 'next/link'

export default async function DashboardPage() {
  const t = await getTranslations('dashboard')

  const quickLinks = [
    { href: '../tree', icon: GitBranch, label: t('tree'), color: 'bg-blue-50 text-blue-700' },
    { href: '../members', icon: Users, label: t('members'), color: 'bg-green-50 text-green-700' },
    {
      href: '../events',
      icon: Calendar,
      label: t('events'),
      color: 'bg-accent text-accent-foreground',
    },
    {
      href: '../documents',
      icon: FileText,
      label: t('documents'),
      color: 'bg-purple-50 text-purple-700',
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-foreground font-serif text-2xl">{t('welcome')}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('overview')}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {quickLinks.map(({ href, icon: Icon, label, color }) => (
          <Link
            key={href}
            href={href}
            className="border-border bg-card hover:border-input flex flex-col items-center gap-2 rounded-2xl border p-4 shadow-xs transition-all hover:shadow-md"
          >
            <div className={`rounded-xl p-3 ${color}`}>
              <Icon className="h-5 w-5" />
            </div>
            <span className="text-foreground text-xs font-medium">{label}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
