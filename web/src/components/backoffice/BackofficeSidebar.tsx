'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  Users,
  TreeDeciduous,
  Building2,
  LayoutDashboard,
  ChevronRight,
  LogOut,
} from 'lucide-react'
import { useAuth } from '@/lib/hooks/useAuth'
import { cn } from '@/lib/utils/cn'

const NAV_ITEMS = [
  { href: 'dashboard', labelKey: 'nav_dashboard', icon: LayoutDashboard },
  { href: 'members', labelKey: 'nav_members', icon: Users },
  { href: 'clans', labelKey: 'nav_clans', icon: Building2 },
  { href: 'tree', labelKey: 'nav_tree', icon: TreeDeciduous },
] as const

export function BackofficeSidebar({ locale }: { locale: string }) {
  const t = useTranslations('Backoffice')
  const { signOut } = useAuth()
  const pathname = usePathname()

  return (
    <aside className="w-60 h-screen flex flex-col bg-gray-950 text-gray-100 shrink-0 fixed left-0 top-0">
      {/* Brand */}
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-gray-800">
        <span className="text-primary-400 font-bold text-lg font-serif">FR</span>
        <div className="leading-tight">
          <p className="text-xs font-semibold">FamilyRoots</p>
          <p className="text-[10px] text-gray-400">Backoffice</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
          const fullHref = `/${locale}/backoffice/${href}`
          const active = pathname.startsWith(fullHref)
          return (
            <Link
              key={href}
              href={fullHref}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                active
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {t(labelKey)}
              {active && <ChevronRight className="ml-auto h-3 w-3 opacity-60" />}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-gray-800">
        <button
          onClick={() => signOut()}
          className="flex w-full items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
