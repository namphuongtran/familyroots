import { getCapabilities, type CapabilitySet } from '@/domain/capability/capability'
import { asClanRole } from '@/domain/invitation/invitation'

/**
 * Every key `getCapabilities` returns, each false. Built here rather than added to
 * `domain/capability`, which ADR-061 § 1 keeps unchanged. Not `getCapabilities('viewer')`: that
 * is all false only because rbac.md gives viewer no conditional row today.
 */
export const NO_CAPABILITIES: CapabilitySet = Object.freeze(
  Object.fromEntries(Object.keys(getCapabilities('admin')).map((key) => [key, false])),
) as CapabilitySet

/**
 * What a membership role grants, as the domain `CapabilitySet`. The client hook
 * (`useCapabilities`) and the server guard (`server/guard.ts`) both read it, so a screen and the
 * route guarding it cannot disagree about a role.
 *
 * No role, or a role that is not one of the three clan roles (`asClanRole`), grants nothing.
 */
export function capabilitiesOf(role: string | null | undefined): CapabilitySet {
  const clanRole = role == null ? null : asClanRole(role)
  return clanRole === null ? NO_CAPABILITIES : getCapabilities(clanRole)
}
