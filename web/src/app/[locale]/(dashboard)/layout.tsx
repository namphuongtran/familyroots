'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { landingPath, useSession } from '@/features/auth'
import { readCurrentClanId, writeClanCookie } from '@/shared/http/context.client'
import { useUIStore } from '@/store/ui.store'
import { cn } from '@/lib/utils/cn'

/**
 * **Interim, until #186 makes this a server layout** (ADR-061 § 3). It redirects on the client,
 * from the domain access state, to wherever `landingPath` sends that state.
 *
 * It reads the session through `useSession`, as `Header` does, so the two share one query and
 * the page sends one `GET /auth/me` between them. Before #183 each hydrated a zustand store on
 * its own and the page ran away (`web/CLAUDE.md`, "The `(dashboard)` group runs away").
 *
 * A ready user's active clan is written back to the cookie when the cookie names another one,
 * which happens when the cookie names a clan the user has since left and they hold one other.
 * Clan-scoped requests read the cookie, so the two must agree before the page asks for anything.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { access, isError, refetch } = useSession()
  const router = useRouter()
  const locale = useLocale()
  const t = useTranslations('common')
  const { sidebarOpen } = useUIStore()

  useEffect(() => {
    if (access === null) return
    if (access.kind === 'ready') {
      if (readCurrentClanId() !== access.activeClan.clanId) {
        writeClanCookie(access.activeClan.clanId)
      }
      return
    }
    router.push(landingPath(access, locale))
  }, [access, locale, router])

  if (access === null && isError) {
    return (
      <div className="bg-background flex min-h-screen flex-col items-center justify-center gap-3 px-4">
        <p role="alert" className="text-foreground text-sm">
          {t('error')}
        </p>
        <button
          type="button"
          onClick={() => void refetch().catch(() => {})}
          className="bg-primary text-primary-foreground hover:bg-primary-hover focus:ring-ring rounded-full px-4 py-2 text-sm font-medium focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
        >
          {t('retry')}
        </button>
      </div>
    )
  }

  if (access === null) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <div className="border-primary h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
      </div>
    )
  }

  if (access.kind !== 'ready') return null

  return (
    <div className="bg-background flex h-screen overflow-hidden">
      <Sidebar />
      <div
        className={cn(
          'flex min-w-0 flex-1 flex-col transition-all duration-200',
          sidebarOpen ? 'ml-56' : 'ml-14',
        )}
      >
        <Header />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  )
}
