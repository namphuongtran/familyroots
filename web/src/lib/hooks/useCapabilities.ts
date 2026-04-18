'use client'

import { useMemo } from 'react'
import { deriveCapabilities } from '@/application/auth/use-cases/capabilities'
import { useAuthStore } from '@/store/auth.store'

export function useCapabilities() {
  const { user, currentClanId, isPendingApproval } = useAuthStore()

  return useMemo(
    () =>
      deriveCapabilities(user, {
        hasActiveClan: Boolean(currentClanId),
        isPendingApproval,
      }),
    [currentClanId, isPendingApproval, user],
  )
}
