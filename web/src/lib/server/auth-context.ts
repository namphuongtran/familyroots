import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import type { UserClanMembership } from '@/lib/types'
import { createClientOrNull as createSupabaseServerClientOrNull } from '@/lib/supabase/server'
import { isSupabaseConfigured } from '@/lib/supabase/config'

export type ServerAppRole = 'viewer' | 'editor' | 'admin' | 'super_admin'

interface ServerAuthContext {
  accessToken: string
  userId: string
  preferredLocale: string
  clanMemberships: UserClanMembership[]
  currentClanId?: string
  currentClanRole?: Exclude<ServerAppRole, 'super_admin'>
}

const CURRENT_CLAN_COOKIE = 'current_clan_id'

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'
}

export async function getServerAuthContext(): Promise<ServerAuthContext | null> {
  if (!isSupabaseConfigured()) {
    return null
  }

  const supabase = await createSupabaseServerClientOrNull()
  if (!supabase) {
    return null
  }
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token || !session.user) {
    return null
  }

  const cookieStore = await cookies()
  const preferredClanId = cookieStore.get(CURRENT_CLAN_COOKIE)?.value

  const membershipResponse = await fetch(`${getApiBaseUrl()}/me/clans`, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      'Accept-Language': 'vi',
    },
    cache: 'no-store',
  })

  if (!membershipResponse.ok) {
    return {
      accessToken: session.access_token,
      userId: session.user.id,
      preferredLocale: 'vi',
      clanMemberships: [],
      currentClanId: undefined,
      currentClanRole: undefined,
    }
  }

  const membershipData = (await membershipResponse.json()) as {
    clans: UserClanMembership[]
  }
  const clanMemberships = membershipData.clans ?? []
  const currentClanId = resolveCurrentClanId(clanMemberships, preferredClanId)
  const currentMembership = clanMemberships.find((membership) => membership.clan_id === currentClanId)

  return {
    accessToken: session.access_token,
    userId: session.user.id,
    preferredLocale: 'vi',
    clanMemberships,
    currentClanId,
    currentClanRole: currentMembership?.role,
  }
}

export async function requireServerRole(
  requiredRole: ServerAppRole | ServerAppRole[],
  locale: string,
): Promise<ServerAuthContext> {
  const authContext = await getServerAuthContext()

  if (!authContext) {
    redirect(`/${locale}/login`)
  }

  const requiredRoles = Array.isArray(requiredRole) ? requiredRole : [requiredRole]

  if (requiredRoles.includes('super_admin')) {
    const platformCheck = await fetch(`${getApiBaseUrl()}/platform/metrics`, {
      headers: {
        Authorization: `Bearer ${authContext.accessToken}`,
        'Accept-Language': 'vi',
      },
      cache: 'no-store',
    })

    if (platformCheck.ok) {
      return authContext
    }

    if (requiredRoles.length === 1) {
      redirect(`/${locale}/dashboard`)
    }
  }

  if (!authContext.currentClanId && authContext.clanMemberships.length > 1) {
    redirect(`/${locale}/select-clan`)
  }

  if (!authContext.currentClanId && authContext.clanMemberships.length === 0) {
    redirect(`/${locale}/pending-approval`)
  }

  if (
    authContext.currentClanRole &&
    requiredRoles.some((role) => role !== 'super_admin' && hasMinServerRole(authContext.currentClanRole!, role))
  ) {
    return authContext
  }

  redirect(`/${locale}/dashboard`)
}

export function hasMinServerRole(
  userRole: Exclude<ServerAppRole, 'super_admin'>,
  minRole: Exclude<ServerAppRole, 'super_admin'>,
): boolean {
  const hierarchy = {
    viewer: 0,
    editor: 1,
    admin: 2,
  } as const

  return hierarchy[userRole] >= hierarchy[minRole]
}

function resolveCurrentClanId(
  memberships: UserClanMembership[],
  preferredClanId?: string,
): string | undefined {
  if (preferredClanId && memberships.some((membership) => membership.clan_id === preferredClanId)) {
    return preferredClanId
  }

  if (memberships.length === 1) {
    return memberships[0]?.clan_id
  }

  return undefined
}
