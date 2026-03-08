'use client'

import { useTranslations } from 'next-intl'
import { LogOut, User, ChevronDown } from 'lucide-react'
import { LocaleSwitcher } from './LocaleSwitcher'
import { useAuth } from '@/lib/hooks/useAuth'
import { useAuthStore } from '@/store/auth.store'
import { cn } from '@/lib/utils/cn'
import { useState } from 'react'

interface HeaderProps {
  title?: string
}

export function Header({ title }: HeaderProps) {
  const t = useTranslations()
  const { signOut } = useAuth()
  const { user } = useAuthStore()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="h-16 flex items-center justify-between px-6 bg-white border-b border-cream-200 shrink-0">
      <h1 className="text-lg font-serif font-semibold text-gray-800 truncate">
        {title ?? ''}
      </h1>

      <div className="flex items-center gap-3">
        <LocaleSwitcher />

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-cream-100 text-sm text-gray-700"
          >
            <User className="h-4 w-4" />
            <span className="hidden sm:block max-w-[120px] truncate">
              {user?.full_name}
            </span>
            <ChevronDown className="h-3 w-3 opacity-60" />
          </button>

          {menuOpen && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-10"
                onClick={() => setMenuOpen(false)}
              />
              <div
                className={cn(
                  'absolute right-0 top-full mt-1 w-48 bg-white rounded-lg shadow-lg border border-cream-200 z-20',
                  'py-1',
                )}
              >
                <div className="px-3 py-2 border-b border-cream-100">
                  <p className="text-xs font-medium text-gray-900 truncate">
                    {user?.full_name}
                  </p>
                  <p className="text-xs text-gray-500 truncate">{user?.email}</p>
                </div>
                <button
                  onClick={signOut}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  {t('auth.logout')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
