/**
 * Zod DTOs for the auth wire shapes this slice reads, constrained to
 * `src/generated/api-types.ts`, plus the mappers into `@/domain/session/session`.
 *
 * Same discipline as `features/persons/model/person-dto.ts`: every schema mirrors one generated
 * type field for field, optionality and nullability included, and each
 * `assert*MatchesGenerated` below only compiles while the two agree. A contract change fails
 * `pnpm type-check` here, not at runtime.
 *
 * Write bodies (`RegisterRequest`, `AuthenticatedOnboardingRequest`, `UserUpdateRequest`,
 * `ResendVerificationRequest`) get no schema, for the persons slice's reason: the caller builds
 * them and TypeScript checks the shape at the call site.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { Membership, Profile } from '@/domain/session/session'

const nullableString = z.string().nullable().optional()

/** `backend/app/schemas/auth.py`, `UserProfile.platform_role`. #181. */
const PLATFORM_ROLES = ['user', 'super_admin'] as const

/** Mirrors `components["schemas"]["UserProfile"]`, the body of `GET /auth/me`. */
export const userProfileDtoSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  clan_id: nullableString,
  clan_name: nullableString,
  role: nullableString,
  is_approved: z.boolean(),
  has_pending_membership: z.boolean(),
  person_id: nullableString,
  preferred_locale: z.string(),
  platform_role: z.enum(PLATFORM_ROLES),
})

export type UserProfileDto = z.infer<typeof userProfileDtoSchema>

export function assertUserProfileDtoMatchesGenerated(
  dto: UserProfileDto,
): components['schemas']['UserProfile'] {
  return dto
}

/**
 * `clan_id`, `clan_name`, `role` and `is_approved` are left on the wire. They describe one
 * approved membership the backend picked (`docs/contracts/rest-auth-api.md`, "Which membership
 * login returns"), which is a landing hint. The memberships list is what this app decides on,
 * and the legacy client's fallback to this `clan_id` is the disagreement ADR-061 § 3 removed.
 */
export function toProfile(dto: UserProfileDto): Profile {
  return {
    userId: dto.id,
    email: dto.email,
    fullName: dto.full_name,
    preferredLocale: dto.preferred_locale,
    platformRole: dto.platform_role,
    hasPendingMembership: dto.has_pending_membership,
  }
}

/** Mirrors `components["schemas"]["UserClanMembership"]`, one item of `GET /me/clans`. */
export const userClanMembershipDtoSchema = z.object({
  clan_id: z.string(),
  clan_name: z.string(),
  clan_slug: z.string(),
  role: z.string(),
  joined_at: nullableString,
})

export type UserClanMembershipDto = z.infer<typeof userClanMembershipDtoSchema>

export function assertUserClanMembershipDtoMatchesGenerated(
  dto: UserClanMembershipDto,
): components['schemas']['UserClanMembership'] {
  return dto
}

export function toMembership(dto: UserClanMembershipDto): Membership {
  return {
    clanId: dto.clan_id,
    clanName: dto.clan_name,
    clanSlug: dto.clan_slug,
    role: dto.role,
  }
}

/** Mirrors `components["schemas"]["ClanSwitchResponse"]`, `POST /me/clans/{id}/select`. */
export const clanSwitchResponseDtoSchema = z.object({
  clan_id: z.string(),
  clan_name: z.string(),
  clan_slug: z.string(),
  role: z.string(),
  message: z.string(),
})

export function assertClanSwitchResponseDtoMatchesGenerated(
  dto: z.infer<typeof clanSwitchResponseDtoSchema>,
): components['schemas']['ClanSwitchResponse'] {
  return dto
}

/** Mirrors `components["schemas"]["MessageData"]`: register, resend-verification, `PATCH /me`. */
export const messageDataDtoSchema = z.object({ message: z.string() })

export function assertMessageDataDtoMatchesGenerated(
  dto: z.infer<typeof messageDataDtoSchema>,
): components['schemas']['MessageData'] {
  return dto
}

/**
 * What `POST /auth/register` answers: one localised sentence. The route is non-enumerating
 * (ADR-021), so it carries no user, clan or approval state. The register screen shows it.
 */
export interface RegistrationReceived {
  message: string
}

/** Mirrors `components["schemas"]["RegisterResponse"]`, `POST /auth/onboard`. */
export const registerResponseDtoSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  full_name: z.string(),
  clan_id: z.string(),
  is_approved: z.boolean(),
  message: z.string(),
})

export function assertRegisterResponseDtoMatchesGenerated(
  dto: z.infer<typeof registerResponseDtoSchema>,
): components['schemas']['RegisterResponse'] {
  return dto
}

/** What onboarding attached the user to. */
export interface OnboardResult {
  clanId: string
  isApproved: boolean
}

/**
 * The two join requests, without `clan_id`. ADR-057 § 2 made the typed identifier the clan
 * code, and the backend refuses `clan_code` and `clan_id` together with a 422
 * `auth.clan_code_and_id_both_given` (`docs/contracts/rest-auth-api.md`, "The join identifier").
 * The generated types still declare `clan_id` for the one release it is accepted; leaving it out
 * here means nothing in this app can build the pair that is refused.
 */
export type RegisterInput = Omit<components['schemas']['RegisterRequest'], 'clan_id'>
export type OnboardInput = Omit<components['schemas']['AuthenticatedOnboardingRequest'], 'clan_id'>
export type ProfileUpdate = components['schemas']['UserUpdateRequest']
