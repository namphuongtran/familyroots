/**
 * The **Session** (`CONTEXT.md`, "Belonging"): who is signed in, and the approved memberships
 * they hold. It never says which clan they act in. That is the **Active clan**, which
 * `access-state.ts` resolves from these memberships and the `current_clan_id` cookie.
 *
 * Plain types, same as the rest of `src/domain/`. `features/auth/model/session-dto.ts` maps
 * the wire shapes of `GET /auth/me` and `GET /me/clans` into these.
 */

/**
 * `docs/contracts/rest-auth-api.md`, "Profile field semantics": always present, and
 * `"super_admin"` exactly when the platform routes would admit the user. It is independent of
 * any clan role, and it routes, it does not authorize.
 */
export type PlatformRole = 'user' | 'super_admin'

/** The profile half of `GET /auth/me` this app reads. */
export interface Profile {
  readonly userId: string
  readonly email: string
  readonly fullName: string
  readonly preferredLocale: string
  readonly platformRole: PlatformRole
  /** True when the user has any membership no admin has approved yet. */
  readonly hasPendingMembership: boolean
}

/**
 * One **approved** membership, from `GET /me/clans`, which lists approved memberships only.
 *
 * `role` is the string the wire sent. The generated type says `role: string`, so narrowing it
 * here would be a claim the contract does not make. `asClanRole`
 * (`@/domain/invitation/invitation`) decides whether it is one of the three clan roles.
 */
export interface Membership {
  readonly clanId: string
  readonly clanName: string
  readonly clanSlug: string
  readonly role: string
}

export interface Session {
  readonly profile: Profile
  readonly memberships: readonly Membership[]
}
