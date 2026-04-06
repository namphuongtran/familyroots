'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  LayoutDashboard,
  GitFork,
  Users,
  CalendarDays,
  FolderOpen,
  Settings,
  Shield,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { useUIStore } from '@/store/ui.store'
import { useAuthStore } from '@/store/auth.store'

interface NavItem {
  href: string
  labelKey: string
  icon: React.ComponentType<{ className?: string }>
  adminOnly?: boolean
  superAdminOnly?: boolean
}

const navItems: NavItem[] = [
  { href: '/dashboard', labelKey: 'nav.dashboard', icon: LayoutDashboard },
  { href: '/tree', labelKey: 'nav.tree', icon: GitFork },
  { href: '/members', labelKey: 'nav.members', icon: Users },
  { href: '/events', labelKey: 'nav.events', icon: CalendarDays },
  { href: '/documents', labelKey: 'nav.documents', icon: FolderOpen },
  { href: '/admin/users', labelKey: 'nav.admin', icon: Settings, adminOnly: true },
  { href: '/platform/clans', labelKey: 'nav.platform', icon: Shield, superAdminOnly: true },
]

export function Sidebar() {
  const t = useTranslations()
  const pathname = usePathname()
  const { sidebarOpen, toggleSidebar } = useUIStore()
  const { user } = useAuthStore()

  const role = user?.role
  const isAdmin = role === 'admin' || role === 'super_admin'
  const isSuperAdmin = role === 'super_admin'

  const visibleItems = navItems.filter((item) => {
    if (item.superAdminOnly && !isSuperAdmin) return false
    if (item.adminOnly && !isAdmin) return false
    return true
  })

  return (
    <aside
      className={cn(
        'flex flex-col h-screen bg-cream-50 border-r border-cream-200 transition-all duration-300 shrink-0',
        sidebarOpen ? 'w-56' : 'w-16',
      )}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-3 border-b border-cream-200">
        {sidebarOpen && (
          <span className="font-serif font-bold text-primary-700 text-lg truncate ml-1">
            Gia Phả
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="ml-auto p-1.5 rounded-md hover:bg-cream-200 text-gray-500 hover:text-gray-700"
          aria-label={sidebarOpen ? 'Thu gọn' : 'Mở rộng'}
        >
          {sidebarOpen ? (
            <ChevronLeft className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Clan name */}
      {sidebarOpen && user?.clan_name && (
        <div className="px-4 py-2 border-b border-cream-200">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Dòng họ</p>
          <p className="text-sm font-medium text-primary-700 truncate">
            {user.clan_name}
          </p>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {visibleItems.map((item) => {
          const Icon = item.icon
          // Match locale-prefixed path: /vi/dashboard → /dashboard
          const isActive = pathname.includes(item.href)

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 mx-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-100 text-primary-700'
                  : 'text-gray-600 hover:bg-cream-200 hover:text-gray-900',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {sidebarOpen && (
                <span className="truncate">{t(item.labelKey as Parameters<typeof t>[0])}</span>
              )}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
