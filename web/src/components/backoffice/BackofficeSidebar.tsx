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
    <aside className="w-60 h-screen flex flex-col bg-muted text-foreground shrink-0 fixed left-0 top-0">
      {/* Brand */}
      <div className="h-16 flex items-center gap-2.5 px-5 mb-2">
        {/*
          ADR-046 ("The backoffice aside stops being inverted and becomes a
          surface step") converted this aside from a hand-built bg-gray-950
          to the `muted` token, so every ink here is now a pair
          contrast.test.ts already runs against `muted` in both schemes. The
          mark used to take `primary-container` because `primary` measured
          only 2.68:1 on the old #030712 ground; on `muted` the order swaps:
          measured 2026-08-22, `primary` is 6.83:1 in light and 8.20:1 in
          dark, while `primary-container` drops to 1.20:1 and 1.50:1. See the
          ADR for the full table and the one-cause explanation (a token
          placed on a ground outside the token system fails in one theme or
          the other, because the ink moves and the ground cannot).
        */}
        <span className="text-primary font-bold text-lg font-serif">FR</span>
        <div className="leading-tight">
          <p className="text-xs text-foreground">{t('rail_label')}</p>
          <p className="text-xs font-semibold">FamilyRoots</p>
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
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-card hover:text-foreground',
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
      <div className="px-3 py-4 mt-2">
        <button
          onClick={() => signOut()}
          className="flex w-full items-center gap-3 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-card hover:text-foreground transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
