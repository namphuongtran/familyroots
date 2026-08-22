import { getTranslations } from 'next-intl/server'
import { Users, GitBranch, Calendar, FileText } from 'lucide-react'
import Link from 'next/link'

export default async function DashboardPage() {
  const t = await getTranslations('dashboard')

  const quickLinks = [
    { href: '../tree', icon: GitBranch, label: t('tree'), color: 'bg-blue-50 text-blue-700' },
    { href: '../members', icon: Users, label: t('members'), color: 'bg-green-50 text-green-700' },
    { href: '../events', icon: Calendar, label: t('events'), color: 'bg-amber-50 text-amber-700' },
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
        <h1 className="font-serif text-2xl text-gray-800">{t('welcome')}</h1>
        <p className="mt-1 text-sm text-gray-500">{t('overview')}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {quickLinks.map(({ href, icon: Icon, label, color }) => (
          <Link
            key={href}
            href={href}
            className="flex flex-col items-center gap-2 rounded-2xl border border-gray-100 bg-white p-4 shadow-xs transition-all hover:border-gray-200 hover:shadow-md"
          >
            <div className={`rounded-xl p-3 ${color}`}>
              <Icon className="h-5 w-5" />
            </div>
            <span className="text-xs font-medium text-gray-700">{label}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
