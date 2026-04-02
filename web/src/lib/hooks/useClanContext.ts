'use client'

import { useMemo } from 'react'
import { useAuth } from '@/lib/hooks/useAuth'

export function useClanContext() {
  const { clanMemberships, currentClanId, selectClan, user } = useAuth()

  const activeClan = useMemo(
    () => clanMemberships.find((clan) => clan.clan_id === currentClanId),
    [clanMemberships, currentClanId],
  )

  return {
    clanMemberships,
    currentClanId,
    activeClan,
    canSwitchClan: clanMemberships.length > 1,
    selectClan,
    role: user?.role,
  }
}
