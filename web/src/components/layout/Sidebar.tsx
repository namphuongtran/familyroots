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
import { useSession } from '@/features/auth'
import { useUIStore } from '@/store/ui.store'

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
  const { session, activeClan } = useSession()

  // The active clan's role, and the platform role beside it. They are independent: a clan role
  // is never `super_admin` (`docs/architecture/rbac.md:29-35`), which is why the old reading of
  // `role === 'super_admin'` never showed the platform link to anyone.
  const isAdmin = activeClan?.role === 'admin'
  const isSuperAdmin = session?.profile.platformRole === 'super_admin'

  const visibleItems = navItems.filter((item) => {
    if (item.superAdminOnly && !isSuperAdmin) return false
    if (item.adminOnly && !isAdmin) return false
    return true
  })

  return (
    <aside
      className={cn(
        'bg-cream-50 border-cream-200 flex h-screen shrink-0 flex-col border-r transition-all duration-300',
        sidebarOpen ? 'w-56' : 'w-16',
      )}
    >
      {/* Logo */}
      <div className="border-cream-200 flex h-16 items-center border-b px-3">
        {sidebarOpen && (
          <span className="text-primary ml-1 truncate font-serif text-lg font-bold">Gia Phả</span>
        )}
        <button
          onClick={toggleSidebar}
          className="hover:bg-cream-200 text-muted-foreground hover:text-foreground ml-auto rounded-md p-1.5"
          aria-label={sidebarOpen ? t('common.collapse') : t('common.expand')}
        >
          {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
      </div>

      {/* Clan name */}
      {sidebarOpen && activeClan && (
        <div className="border-cream-200 border-b px-4 py-2">
          <p className="text-muted-foreground text-xs tracking-wide uppercase">
            {t('common.clan')}
          </p>
          <p className="text-primary truncate text-sm font-medium">{activeClan.clanName}</p>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3">
        {visibleItems.map((item) => {
          const Icon = item.icon
          // Match locale-prefixed path: /vi/dashboard → /dashboard
          const isActive = pathname.includes(item.href)

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'mx-2 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-container text-primary-container-foreground'
                  : 'hover:bg-cream-200 text-muted-foreground hover:text-foreground',
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
