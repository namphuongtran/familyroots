import type {
  AuthProfileRepository,
  AuthSessionPort,
  SessionUser,
} from '@/application/auth/ports/auth-repository'
import type { UserClanMembership, UserProfile } from '@/lib/types'

export interface HydratedAuthContext {
  user: UserProfile | null
  clanMemberships: UserClanMembership[]
  currentClanId?: string
  activeMembership?: UserClanMembership
  isPendingApproval: boolean
  needsOnboarding: boolean
  needsClanSelection: boolean
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function asBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined
}

export function mapSessionUserToProfile(user: SessionUser): UserProfile {
  const meta = user.metadata ?? {}

  return {
    id: user.id,
    email: user.email,
    full_name: asString(meta.full_name) ?? user.email,
    clan_id: undefined,
    clan_name: undefined,
    role: undefined,
    is_approved: false,
    has_pending_membership: false,
    person_id: undefined,
    preferred_locale: (asString(meta.preferred_locale) as UserProfile['preferred_locale']) ?? 'vi',
    platform_role: undefined,
  }
}

export async function hydrateAuthContext(
  sessionPort: AuthSessionPort,
  profileRepository: AuthProfileRepository,
  preferredClanId?: string,
): Promise<HydratedAuthContext> {
  const sessionUser = await sessionPort.getSessionUser()
  if (!sessionUser) {
    return {
      user: null,
      clanMemberships: [],
      currentClanId: undefined,
      activeMembership: undefined,
      isPendingApproval: false,
      needsOnboarding: false,
      needsClanSelection: false,
    }
  }

  const fallbackProfile = mapSessionUserToProfile(sessionUser)

  try {
    const [profile, memberships] = await Promise.all([
      profileRepository.getMe(),
      profileRepository.listMyClans(),
    ])

    const currentClanId = resolveCurrentClanId(memberships.clans, preferredClanId, profile.clan_id)
    const activeMembership = memberships.clans.find(
      (membership) => membership.clan_id === currentClanId,
    )
    const mergedProfile = {
      ...fallbackProfile,
      ...profile,
      clan_id: currentClanId,
      clan_name: activeMembership?.clan_name ?? profile.clan_name,
      role: activeMembership?.role ?? profile.role,
      is_approved: memberships.clans.length > 0 || profile.is_approved,
      has_pending_membership: profile.has_pending_membership ?? false,
      preferred_locale: profile.preferred_locale ?? fallbackProfile.preferred_locale,
    }

    const hasApprovedClanMembership = memberships.clans.length > 0
    const hasPendingMembership = mergedProfile.has_pending_membership === true
    const isPlatformOnlyUser = Boolean(mergedProfile.platform_role)

    return {
      user: mergedProfile,
      clanMemberships: memberships.clans,
      currentClanId,
      activeMembership,
      isPendingApproval: !isPlatformOnlyUser && !hasApprovedClanMembership && hasPendingMembership,
      needsOnboarding: !isPlatformOnlyUser && !hasApprovedClanMembership && !hasPendingMembership,
      needsClanSelection: memberships.clans.length > 1 && !currentClanId,
    }
  } catch {
    // Keep a minimal identity-only fallback; do not derive clan or role truth from Supabase metadata.
    return {
      user: fallbackProfile,
      clanMemberships: [],
      currentClanId: undefined,
      activeMembership: undefined,
      isPendingApproval: false,
      needsOnboarding: false,
      needsClanSelection: false,
    }
  }
}

export async function selectActiveClan(
  profileRepository: AuthProfileRepository,
  clanId: string,
): Promise<string> {
  const result = await profileRepository.selectClan(clanId)
  return result.clan_id
}

function resolveCurrentClanId(
  memberships: UserClanMembership[],
  preferredClanId?: string,
  profileClanId?: string,
): string | undefined {
  const validClanIds = new Set(memberships.map((membership) => membership.clan_id))

  if (preferredClanId && validClanIds.has(preferredClanId)) {
    return preferredClanId
  }

  if (profileClanId && validClanIds.has(profileClanId)) {
    return profileClanId
  }

  if (memberships.length === 1) {
    return memberships[0]?.clan_id
  }

  return undefined
}
