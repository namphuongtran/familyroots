import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Locale = 'vi' | 'en' | 'zh' | 'fr'

interface UIState {
  sidebarOpen: boolean
  locale: Locale
  treeMaxGenerations: number
  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void
  setLocale: (locale: Locale) => void
  setTreeMaxGenerations: (n: number) => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      locale: 'vi',
      treeMaxGenerations: 6,
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setLocale: (locale) => {
        set({ locale })
        if (typeof window !== 'undefined') {
          localStorage.setItem('preferred_locale', locale)
        }
      },
      setTreeMaxGenerations: (n) => set({ treeMaxGenerations: n }),
    }),
    { name: 'ui-store' },
  ),
)
