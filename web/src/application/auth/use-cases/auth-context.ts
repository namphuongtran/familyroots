import type {
  AuthProfileRepository,
  AuthSessionPort,
  SessionUser,
} from '@/application/auth/ports/auth-repository'
import type {
  UserClanMembership,
  UserProfile,
} from '@/lib/types'

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
    clan_id: asString(meta.clan_id),
    clan_name: asString(meta.clan_name),
    role:
      (asString(meta.clan_role) as UserProfile['role']) ??
      (asString(meta.role) as UserProfile['role']),
    is_approved: asBoolean(meta.is_approved) ?? false,
    person_id: asString(meta.person_id),
    preferred_locale:
      (asString(meta.preferred_locale) as UserProfile['preferred_locale']) ?? 'vi',
    platform_role:
      (asString(meta.platform_role) as UserProfile['platform_role']) ?? undefined,
  }
}

export async function hydrateAuthContext(
  sessionPort: AuthSessionPort,
  profileRepository: AuthProfileRepository,
): Promise<{
  user: UserProfile | null
  clanMemberships: UserClanMembership[]
  currentClanId?: string
}> {
  const sessionUser = await sessionPort.getSessionUser()
  if (!sessionUser) {
    return { user: null, clanMemberships: [], currentClanId: undefined }
  }

  const fallbackProfile = mapSessionUserToProfile(sessionUser)

  try {
    const [profile, memberships] = await Promise.all([
      profileRepository.getMe(),
      profileRepository.listMyClans(),
    ])

    return {
      user: {
        ...fallbackProfile,
        ...profile,
        preferred_locale: profile.preferred_locale ?? fallbackProfile.preferred_locale,
      },
      clanMemberships: memberships.clans,
      currentClanId: profile.clan_id ?? memberships.clans[0]?.clan_id,
    }
  } catch {
    // If backend profile endpoints are unavailable, keep the session fallback.
    return {
      user: fallbackProfile,
      clanMemberships: [],
      currentClanId: fallbackProfile.clan_id,
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