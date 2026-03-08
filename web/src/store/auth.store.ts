import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserProfile } from '@/lib/types'

interface AuthState {
  user: UserProfile | null
  isLoading: boolean
  setUser: (user: UserProfile | null) => void
  setLoading: (loading: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isLoading: true,
      setUser: (user) => set({ user, isLoading: false }),
      setLoading: (isLoading) => set({ isLoading }),
      clear: () => set({ user: null, isLoading: false }),
    }),
    {
      name: 'auth-store',
      // Only persist non-sensitive fields
      partialize: (state) => ({ user: state.user }),
    },
  ),
)
