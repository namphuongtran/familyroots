import type { UserProfile } from '@/lib/types'

export interface CapabilitySet {
  canManageClan: boolean
  canEditPersons: boolean
  canDeletePersons: boolean
  canEditRelationships: boolean
  canDeleteRelationships: boolean
  canUploadDocuments: boolean
  canDeleteDocuments: boolean
  canEditEvents: boolean
  canDeleteEvents: boolean
  canAccessPlatform: boolean
}

const EMPTY_CAPABILITIES: CapabilitySet = {
  canManageClan: false,
  canEditPersons: false,
  canDeletePersons: false,
  canEditRelationships: false,
  canDeleteRelationships: false,
  canUploadDocuments: false,
  canDeleteDocuments: false,
  canEditEvents: false,
  canDeleteEvents: false,
  canAccessPlatform: false,
}

export function deriveCapabilities(
  user: UserProfile | null,
  options?: {
    hasActiveClan?: boolean
    isPendingApproval?: boolean
  },
): CapabilitySet {
  if (!user || options?.isPendingApproval || options?.hasActiveClan === false) {
    return EMPTY_CAPABILITIES
  }

  const isSuperAdmin = user.platform_role === 'super_admin' || user.role === 'super_admin'
  const role = user.role
  const isAdmin = role === 'admin'
  const isEditor = role === 'editor'

  return {
    canManageClan: isAdmin,
    canEditPersons: isAdmin || isEditor,
    canDeletePersons: isAdmin,
    canEditRelationships: isAdmin || isEditor,
    canDeleteRelationships: isAdmin,
    canUploadDocuments: isAdmin || isEditor,
    canDeleteDocuments: isAdmin,
    canEditEvents: isAdmin || isEditor,
    canDeleteEvents: isAdmin,
    canAccessPlatform: isSuperAdmin,
  }
}
