/**
 * The super-admin's view across clans (docs/contracts/rest-platform-admin-api.md). Plain types
 * only (`domain-is-pure`).
 */

/** One row of `GET /platform/clans`. */
export interface PlatformClanSummary {
  id: string
  name: string
  slug: string
  isActive: boolean
  createdAt: string | null
}

/** `GET /platform/metrics`: independent totals, not derived from any page size. */
export interface PlatformMetrics {
  totalClans: number
  activeClans: number
  suspendedClans: number
  totalMembers: number
  totalUsers: number
}
