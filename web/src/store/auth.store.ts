import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserClanMembership, UserProfile } from '@/lib/types'

interface AuthState {
  user: UserProfile | null
  currentClanId?: string
  clanMemberships: UserClanMembership[]
  isLoading: boolean
  isPendingApproval: boolean
  needsOnboarding: boolean
  needsClanSelection: boolean
  setUser: (user: UserProfile | null) => void
  setCurrentClan: (clanId?: string) => void
  setClanMemberships: (memberships: UserClanMembership[]) => void
  setLoading: (loading: boolean) => void
  setAccessState: (input: {
    isPendingApproval: boolean
    needsOnboarding: boolean
    needsClanSelection: boolean
  }) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      currentClanId: undefined,
      clanMemberships: [],
      isLoading: true,
      isPendingApproval: false,
      needsOnboarding: false,
      needsClanSelection: false,
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
      setAccessState: ({ isPendingApproval, needsOnboarding, needsClanSelection }) =>
        set({ isPendingApproval, needsOnboarding, needsClanSelection }),
      clear: () =>
        set({
          user: null,
          currentClanId: undefined,
          clanMemberships: [],
          isLoading: false,
          isPendingApproval: false,
          needsOnboarding: false,
          needsClanSelection: false,
        }),
    }),
    {
      name: 'auth-store',
      // Only persist non-sensitive fields
      partialize: (state) => ({
        user: state.user,
        currentClanId: state.currentClanId,
        clanMemberships: state.clanMemberships,
        isPendingApproval: state.isPendingApproval,
        needsOnboarding: state.needsOnboarding,
        needsClanSelection: state.needsClanSelection,
      }),
    },
  ),
)
