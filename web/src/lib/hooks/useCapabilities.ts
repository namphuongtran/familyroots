'use client'

import { useMemo } from 'react'
import { deriveCapabilities } from '@/application/auth/use-cases/capabilities'
import { useCurrentClanId } from '@/shared/http/context.client'
import { useAuthStore } from '@/store/auth.store'

export function useCapabilities() {
  const { user, isPendingApproval } = useAuthStore()
  const currentClanId = useCurrentClanId()

  return useMemo(
    () =>
      deriveCapabilities(user, {
        hasActiveClan: Boolean(currentClanId),
        isPendingApproval,
      }),
    [currentClanId, isPendingApproval, user],
  )
}
