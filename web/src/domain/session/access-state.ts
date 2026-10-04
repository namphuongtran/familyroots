/**
 * Where a signed-in user belongs, as one value. ADR-061 § 3.
 *
 * One pure function, so the browser and the server cannot disagree. Before #183 the active clan
 * was resolved twice: the client copy (`application/auth/use-cases/auth-context.ts`) fell back
 * to the profile's `clan_id`, and the server copy (`lib/server/auth-context.ts`) did not. Both
 * call `activeClanOf` below now, and it takes no profile at all.
 *
 * Plain TypeScript: `domain-is-pure` and `domain-imports-only-domain`
 * (`web/.dependency-cruiser.cjs`) fail the build if this file reaches for React, a store, the
 * network, or anything outside `src/domain/`.
 */

import type { Membership, Session } from './session'

export type AccessState =
  | { readonly kind: 'signed-out' }
  /** Only a pending membership: an admin has not approved the join request yet. */
  | { readonly kind: 'pending-approval' }
  /** No membership at all, approved or pending. Spec § 7.2a's onboarding variant. */
  | { readonly kind: 'needs-onboarding' }
  /** Several approved memberships, and the cookie names none of them. */
  | { readonly kind: 'needs-clan-selection' }
  /** A super_admin with no approved membership. They act on the platform, not in a clan. */
  | { readonly kind: 'platform' }
  | { readonly kind: 'ready'; readonly activeClan: Membership }

/**
 * The **Active clan**: the membership the cookie names, when the user holds it; otherwise the
 * only membership, when there is exactly one; otherwise none. A cookie naming a clan the user
 * is not in is treated as no cookie, because the backend would refuse it on every request.
 */
export function activeClanOf(
  memberships: readonly Membership[],
  cookieClanId: string | null,
): Membership | null {
  const named = memberships.find((membership) => membership.clanId === cookieClanId)
  if (named) return named
  return memberships.length === 1 ? memberships[0] : null
}

/**
 * The approved memberships decide first. A user approved in one clan and pending in another is
 * ready in the first: a pending membership grants nothing, so it cannot hold them back.
 */
export function accessStateOf(session: Session | null, cookieClanId: string | null): AccessState {
  if (session === null) return { kind: 'signed-out' }

  if (session.memberships.length === 0) {
    if (session.profile.platformRole === 'super_admin') return { kind: 'platform' }
    if (session.profile.hasPendingMembership) return { kind: 'pending-approval' }
    return { kind: 'needs-onboarding' }
  }

  const activeClan = activeClanOf(session.memberships, cookieClanId)
  return activeClan === null ? { kind: 'needs-clan-selection' } : { kind: 'ready', activeClan }
}
