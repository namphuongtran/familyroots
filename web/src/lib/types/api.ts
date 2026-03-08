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

/** Clan switch response */
export interface ClanSwitchResponse {
  clan_id: string
  clan_name: string
  clan_slug: string
  role: string
  message: string
}

/** User profile returned by /auth/profile and /auth/login */
export interface UserProfile {
  id: string
  email: string
  full_name: string
  clan_id?: string
  clan_name?: string
  role?: 'viewer' | 'editor' | 'admin' | 'super_admin'
  is_approved: boolean
  person_id?: string
  preferred_locale: 'vi' | 'en' | 'zh' | 'fr'
}
