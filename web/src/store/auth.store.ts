import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserClanMembership, UserProfile } from '@/lib/types'

/**
 * Session state only (S-025). The active clan is not here: it used to be
 * `currentClanId`/`setCurrentClan`, persisted to `localStorage` by this same
 * middleware, while `current_clan_id` cookie (S-023) held the same fact for
 * the server to read. Two persisted sources for one fact is exactly the
 * defect this tracker exists to catch, so the clan id was removed rather
 * than kept in sync. Read it with `useCurrentClanId()`
 * (`@/shared/http/context.client`) instead, which reads the cookie — the one
 * source both an RSC and a client component can see.
 */
interface AuthState {
  user: UserProfile | null
  clanMemberships: UserClanMembership[]
  isLoading: boolean
  isPendingApproval: boolean
  needsOnboarding: boolean
  needsClanSelection: boolean
  setUser: (user: UserProfile | null) => void
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
      clanMemberships: [],
      isLoading: true,
      isPendingApproval: false,
      needsOnboarding: false,
      needsClanSelection: false,
      setUser: (user) => set({ user, isLoading: false }),
      setClanMemberships: (clanMemberships) => set({ clanMemberships }),
      setLoading: (isLoading) => set({ isLoading }),
      setAccessState: ({ isPendingApproval, needsOnboarding, needsClanSelection }) =>
        set({ isPendingApproval, needsOnboarding, needsClanSelection }),
      clear: () =>
        set({
          user: null,
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
        clanMemberships: state.clanMemberships,
        isPendingApproval: state.isPendingApproval,
        needsOnboarding: state.needsOnboarding,
        needsClanSelection: state.needsClanSelection,
      }),
    },
  ),
)
