// Generic API response shapes — aligned with actual FastAPI backend responses

/** Standard single-item response wrapper from FastAPI */
export interface ApiResponse<T> {
  data: T
  meta: Record<string, unknown>
}

/** Cursor-paginated list — matches actual backend shape: {data, next_cursor, has_more} */
export interface CursorPage<T> {
  data: T[]
  next_cursor: string | null
  has_more: boolean
}

/** Standard error response from FastAPI */
export interface ApiError {
  error: {
    code: string
    message: string
    detail: Record<string, unknown>
  }
}

/** Tree endpoint response — GET /tree | /tree/subtree | /tree/ancestors */
export interface TreeApiResponse {
  tree: import('./tree').TreeNode
  total_persons: number
  total_generations: number
}

export type TreeAncestorsResponse = import('./tree').TreeNode[]

/** Clan switch response */
export interface ClanSwitchResponse {
  clan_id: string
  clan_name: string
  clan_slug: string
  role: 'viewer' | 'editor' | 'admin'
  message: string
}

export interface UserClanMembership {
  clan_id: string
  clan_name: string
  clan_slug: string
  role: 'viewer' | 'editor' | 'admin'
  joined_at?: string | null
}

/**
 * The port's shape for "the clans I belong to", **not** a wire shape. `GET /me/clans`
 * answers the canonical envelope `{"data": [...]}` and nothing else
 * (`backend/app/api/v1/me.py:25`; `Envelope_list_UserClanMembership__` at
 * `src/generated/api-types.ts:2192-2196`), so the envelope is unwrapped once, in
 * `HttpAuthProfileRepository.listMyClans`, and callers see this.
 *
 * `count: number` was a member of this interface until the authenticated e2e harness (2026-08-26). No
 * endpoint ever sent it and no caller ever read it — `grep -rn "\.count\b" src` found
 * zero readers on that date — so it was a field that only ever had to be invented by
 * whoever constructed one. Removed rather than made optional: an optional field nothing
 * writes and nothing reads is the same fiction with a question mark.
 */
export interface UserClansResponse {
  clans: UserClanMembership[]
}

/** User profile returned by /auth/me and /auth/login */
export interface UserProfile {
  id: string
  email: string
  full_name: string
  clan_id?: string
  clan_name?: string
  role?: 'viewer' | 'editor' | 'admin' | 'super_admin'
  platform_role?: 'super_admin' | null
  is_approved: boolean
  has_pending_membership?: boolean
  person_id?: string
  preferred_locale: 'vi' | 'en' | 'zh' | 'fr'
}
