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
 * the three clan roles. `capabilitiesOf` (`../model/capabilities.ts`) is the mapping, shared with
 * the server guard. The backend still enforces every write (`require_role()`); this only decides
 * what a screen offers.
 */

import { useMemo } from 'react'
import type { CapabilitySet } from '@/domain/capability/capability'
import { capabilitiesOf } from '../model/capabilities'
import { useSession } from './use-session'

export function useCapabilities(): CapabilitySet {
  const activeRole = useSession().activeClan?.role

  return useMemo(() => capabilitiesOf(activeRole), [activeRole])
}
