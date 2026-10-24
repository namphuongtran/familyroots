import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'

/**
 * The `(dashboard)` frame: the sidebar, the header, and the scrolling content column.
 *
 * **The sidebar is in flow, so the column takes no margin.** `Sidebar` is a `shrink-0` flex
 * sibling whose own width follows `ui.store`'s open state, so the column starts where the
 * sidebar ends. Until 2026-10-24 the column also carried `ml-56`/`ml-14` from the March
 * scaffold, which offset it a second time: a 224 px empty band between the rail and the page at
 * every width. It is the backoffice's `fixed`-rail-plus-`ml-*` defect (#174) in the other shape,
 * and `e2e/auth/dashboard.auth.spec.ts` reads where the column starts.
 *
 * It renders and routes nothing. The `(dashboard)` layout is a server layout that admits the
 * request first (`guardClanRoute`, #186), so by the time this mounts the user is ready in an
 * active clan. `Sidebar` and `Header` read the session through `useSession`, one query between
 * them.
 */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-background flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  )
}
