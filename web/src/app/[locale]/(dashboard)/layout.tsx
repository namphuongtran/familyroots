'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { useAuth } from '@/lib/hooks/useAuth'
import { useUIStore } from '@/store/ui.store'
import { cn } from '@/lib/utils/cn'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, isPendingApproval, needsOnboarding, needsClanSelection } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const { sidebarOpen } = useUIStore()
  const locale = pathname.split('/')[1] || 'vi'

  useEffect(() => {
    if (!isLoading && !user) {
      router.push(`/${locale}/login`)
      return
    }

    if (!isLoading && user && isPendingApproval) {
      router.push(`/${locale}/pending-approval`)
      return
    }

    if (!isLoading && user && needsOnboarding) {
      router.push(`/${locale}/register?mode=oauth`)
      return
    }

    if (!isLoading && user && needsClanSelection) {
      router.push(`/${locale}/select-clan`)
    }
  }, [user, isLoading, isPendingApproval, needsOnboarding, locale, needsClanSelection, router])

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!user || isPendingApproval || needsOnboarding) return null

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div
        className={cn(
          'flex flex-col flex-1 min-w-0 transition-all duration-200',
          sidebarOpen ? 'ml-56' : 'ml-14',
        )}
      >
        <Header />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  )
}
