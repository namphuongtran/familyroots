/**
 * Public surface of the `admin` slice: the clan's own profile, its counts, and its accounts
 * (docs/contracts/rest-clans-api.md). `cross-feature-only-via-index` requires every other feature,
 * and `src/app`, to import this slice through this file. The raw `api/` transport is not
 * re-exported: callers get parsed domain values only.
 */

export type {
  ClanProfile,
  ClanProfileUpdate,
  ClanStats,
  ClanUser,
  ClanUsers,
  PendingClanUser,
} from '@/domain/clan/clan-profile'

export type { AdminApiCallOptions } from './server/admin-repository'
export {
  approveClanUser,
  changeClanUserRole,
  CLAN_USERS_PAGE_LIMIT,
  getClanProfile,
  getClanStats,
  listClanUsers,
  rejectClanUser,
  updateClanProfile,
} from './server/admin-repository'
export { adminKeys } from './server/query-keys'

export type { AdminQueryOptions } from './hooks/use-admin-queries'
export {
  useClanProfile,
  useClanStats,
  useClanUserMutations,
  useClanUsers,
  useUpdateClanProfile,
} from './hooks/use-admin-queries'

export { AdminUsersScreen } from './ui/AdminUsersScreen'
export { ClanProfileScreen } from './ui/ClanProfileScreen'
