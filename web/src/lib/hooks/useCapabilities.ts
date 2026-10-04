'use client'

import { useMemo } from 'react'
import { CLAN_ROLES, getCapabilities, type ClanRole } from '@/domain/capability/capability'
import { useSession } from '@/features/auth'

const CLAN_ROLE_SET = new Set<string>(CLAN_ROLES)

function asClanRole(role: string | undefined): ClanRole | undefined {
  return role !== undefined && CLAN_ROLE_SET.has(role) ? (role as ClanRole) : undefined
}

/**
 * **#183: the role comes from the session's access state.** The active clan's membership role
 * when the access state is ready, and no role otherwise, so a pending user, a user who has not
 * chosen among several clans, and a signed-out visitor all get the four `false`s. It used to read
 * `user.role` out of the zustand store beside the cookie. The four names stay until #185 replaces
 * this hook with one that returns the domain `CapabilitySet`.
 *
 * Rewired onto `domain/capability/capability.ts` by the legacy-transport deletion, which closes the
 * `no-orphans` warning that module carried since the capability module landed it with no consumer — see
 * `web/CLAUDE.md`, "Clan capabilities". This hook used to call the legacy
 * `deriveCapabilities` in the now-deleted `src/application/auth/use-cases/capabilities.ts`.
 * Only the four capability names any component still destructures survive here
 * (`grep -rn "useCapabilities()" src` on 2026-08-22); a caller that needs a matrix
 * capability not listed below should call `getCapabilities`/`hasCapability` directly rather
 * than growing this list speculatively.
 *
 * One behaviour changed on purpose, not as a side effect: the legacy module hardcoded
 * `canDeleteEvents: isAdmin`, denying `editor`. `domain/capability.ts`'s own citation
 * (`docs/architecture/rbac.md:78`) grants `editor` event deletion — unlike person,
 * relationship, and document deletion, which really are admin-only. No caller reads
 * `canDeleteEvents` today (`grep -rn "canDeleteEvents" src` before this change found only the
 * legacy definition itself), so nothing regresses; this is recorded so the next reader does
 * not mistake the wider grant for a bug.
 */
export function useCapabilities() {
  const activeRole = useSession().activeClan?.role

  return useMemo(() => {
    const role = asClanRole(activeRole)

    if (!role) {
      return {
        canEditPersons: false,
        canUploadDocuments: false,
        canDeleteDocuments: false,
        canEditRelationships: false,
      }
    }

    const capabilities = getCapabilities(role)
    return {
      canEditPersons: capabilities.editPerson,
      canUploadDocuments: capabilities.uploadDocument,
      canDeleteDocuments: capabilities.deleteDocument,
      canEditRelationships: capabilities.editRelationship,
    }
  }, [activeRole])
}
