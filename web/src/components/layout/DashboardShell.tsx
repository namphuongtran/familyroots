'use client'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { useUIStore } from '@/store/ui.store'
import { cn } from '@/lib/utils/cn'

/**
 * The `(dashboard)` frame: the sidebar, the header, and the scrolling content column. A client
 * component only because the column's offset follows the sidebar's open state in `ui.store`.
 *
 * It renders and routes nothing. The `(dashboard)` layout is a server layout that admits the
 * request first (`guardClanRoute`, #186), so by the time this mounts the user is ready in an
 * active clan. `Sidebar` and `Header` read the session through `useSession`, one query between
 * them.
 */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const { sidebarOpen } = useUIStore()

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
