'use client'

/**
 * What the signed-in user may do in the clan they act in, as the domain `CapabilitySet`.
 * ADR-061 § 4, built by #185. It replaces the legacy hook of the same name in `lib/hooks/`,
 * which returned four renamed booleans. Callers now read the domain names, such as `editPerson`
 * or `deleteDocument`.
 *
 * The role is the active clan's membership role from `useSession()`. `activeClan` is null unless
 * the access state is ready, so a signed-out visitor, a pending user and a user who has not chosen
 * among several clans all get `NO_CAPABILITIES`, and so does a membership whose role is not one of
 * the three clan roles. The backend still enforces every write (`require_role()`); this only
 * decides what a screen offers.
 */

import { useMemo } from 'react'
import { getCapabilities, type CapabilitySet } from '@/domain/capability/capability'
import { asClanRole } from '@/domain/invitation/invitation'
import { useSession } from './use-session'

/**
 * Every key `getCapabilities` returns, each false. Built here rather than added to
 * `domain/capability`, which ADR-061 § 1 keeps unchanged. Not `getCapabilities('viewer')`: that
 * is all false only because rbac.md gives viewer no conditional row today.
 */
const NO_CAPABILITIES: CapabilitySet = Object.freeze(
  Object.fromEntries(Object.keys(getCapabilities('admin')).map((key) => [key, false])),
) as CapabilitySet

export function useCapabilities(): CapabilitySet {
  const activeRole = useSession().activeClan?.role

  return useMemo(() => {
    const role = activeRole === undefined ? null : asClanRole(activeRole)
    return role === null ? NO_CAPABILITIES : getCapabilities(role)
  }, [activeRole])
}
