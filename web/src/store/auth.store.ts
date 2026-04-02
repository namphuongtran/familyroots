import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserClanMembership, UserProfile } from '@/lib/types'

interface AuthState {
  user: UserProfile | null
  currentClanId?: string
  clanMemberships: UserClanMembership[]
  isLoading: boolean
  setUser: (user: UserProfile | null) => void
  setCurrentClan: (clanId?: string) => void
  setClanMemberships: (memberships: UserClanMembership[]) => void
  setLoading: (loading: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      currentClanId: undefined,
      clanMemberships: [],
      isLoading: true,
      setUser: (user) =>
        set((state) => ({
          user,
          isLoading: false,
          currentClanId:
            state.currentClanId ?? user?.clan_id ?? undefined,
        })),
      setCurrentClan: (currentClanId) => set({ currentClanId }),
      setClanMemberships: (clanMemberships) => set({ clanMemberships }),
      setLoading: (isLoading) => set({ isLoading }),
      clear: () =>
        set({
          user: null,
          currentClanId: undefined,
          clanMemberships: [],
          isLoading: false,
        }),
    }),
    {
      name: 'auth-store',
      // Only persist non-sensitive fields
      partialize: (state) => ({
        user: state.user,
        currentClanId: state.currentClanId,
        clanMemberships: state.clanMemberships,
      }),
    },
  ),
)
