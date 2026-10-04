import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { activeClanOf } from '@/domain/session/access-state'
import type { UserClanMembership } from '@/lib/types'
import { createClientOrNull as createSupabaseServerClientOrNull } from '@/shared/supabase/server'
import { isSupabaseConfigured } from '@/shared/supabase/config'

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

/**
 * ADR-056 / ADR-056: `NEXT_PUBLIC_API_URL` is inlined into the JS bundle at
 * `pnpm build` time (Next.js statically replaces every `process.env.NEXT_PUBLIC_*`
 * reference across the whole bundler graph, server code included — the Supabase-variable fix proved this
 * for the two Supabase variables). A server-to-server caller running inside a shared
 * network (compose, or a future container deploy) needs a *different*, network-internal
 * origin than the browser does, and that origin can change per deployment without a
 * rebuild — so it must be read at request time, not baked in.
 *
 * `API_URL` carries no `NEXT_PUBLIC_` prefix, so Next.js never inlines it: this
 * `process.env.API_URL` lookup runs live, in the Node.js runtime, on every call. It
 * takes priority so a deployment shape with two different real origins (compose today;
 * any future shared-network container deploy) can set it. On Vercel, where this
 * function's own request and the browser's request already share one public origin,
 * `API_URL` is simply left unset and this falls through to `NEXT_PUBLIC_API_URL` — the
 * same value the browser bundle got baked with, which is also correct as the
 * server-to-server value there. See ADR-056 for the full decision and cost per
 * deployment shape.
 */
function getApiBaseUrl(): string {
  return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'
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

  // `data`, not `clans`: the canonical envelope. This read said `clans` until the authenticated e2e harness
  // ran the first authenticated e2e case on 2026-08-26 and found `currentClanRole`
  // permanently `undefined`, which silently hid every role-gated element on every
  // server-rendered screen and sent `requireServerRole` to `/pending-approval` for a
  // fully approved admin. Sources: `backend/app/api/v1/me.py:25` returns `{"data":
  // result}`; `src/generated/api-types.ts:2192-2196` types it as
  // `Envelope_list_UserClanMembership__`; `docs/contracts/frontend-integration-guide.md:77`
  // spells it out. The sibling read in `src/infrastructure/auth/http-auth-profile-repository.ts`
  // had the same defect and carries the longer account.
  const membershipData = (await membershipResponse.json()) as {
    data: UserClanMembership[]
  }
  const clanMemberships = membershipData.data ?? []
  // The one clan resolution, shared with the browser since #183. This file used to carry its
  // own copy, which disagreed with the client's: the client fell back to the profile's
  // `clan_id` and this one did not. #186 replaces the rest of this file.
  const currentClanId = activeClanOf(
    clanMemberships.map((membership) => ({
      clanId: membership.clan_id,
      clanName: membership.clan_name,
      clanSlug: membership.clan_slug,
      role: membership.role,
    })),
    preferredClanId ?? null,
  )?.clanId
  const currentMembership = clanMemberships.find(
    (membership) => membership.clan_id === currentClanId,
  )

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
    requiredRoles.some(
      (role) => role !== 'super_admin' && hasMinServerRole(authContext.currentClanRole!, role),
    )
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
