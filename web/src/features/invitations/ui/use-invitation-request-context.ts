'use client'

/**
 * The `RequestContext` for the invitee surface, which is not the same context the
 * rest of the app builds.
 *
 * **`clanId` is always `null`, and that is the contract's rule rather than a
 * shortcut.** `docs/contracts/rest-invitations-api.md:72-74`: "The invitee surface
 * takes no `X-Current-Clan-Id`, and cannot. The invitee is not a member of the clan
 * yet, so there is no clan for them to select. Sending the header has no effect on
 * this route. The token is the authorization." So this hook does not call
 * `useCurrentClanId()` at all. A stale `current_clan_id` cookie left over from an
 * earlier session would otherwise put a header on this request that means nothing
 * here and could only confuse a log.
 *
 * The access token is resolved once, on mount, through `getClientRequestContext()`,
 * exactly as `features/persons/ui/use-persons-request-context.ts` does it, and for
 * the same reason: nothing in this app subscribes to a Supabase auth-state change.
 * `ready` stays false until that resolve finishes, so the screen can keep its
 * Accept button disabled rather than firing a call with no `Authorization` header
 * and turning a signed-in user into a spurious 401.
 *
 * No `refreshAuth` is passed on, same as the persons screens: building a real
 * browser `refreshAuth` needs a decision about where a browser-wide single-flight
 * singleton lives, there is no `features/auth` slice to own it, and inventing one
 * here would smuggle that decision into an unrelated seed. The cost on this screen
 * is small and named: an access token that expired while the page sat open produces
 * the `sign-in-required` state with a link to sign in, instead of refreshing
 * silently.
 */

import { useEffect, useState } from 'react'
import { getClientRequestContext } from '@/shared/http/context.client'
import type { RequestContext } from '@/shared/http/request-context'

export interface InvitationRequestContext {
  context: RequestContext
  /** False until the one-shot client session resolve has completed. */
  ready: boolean
}

export function useInvitationRequestContext(): InvitationRequestContext {
  const [session, setSession] = useState<Pick<RequestContext, 'locale' | 'accessToken'> | null>(
    null,
  )

  useEffect(() => {
    let active = true
    getClientRequestContext().then((resolved) => {
      if (active) setSession({ locale: resolved.locale, accessToken: resolved.accessToken })
    })
    return () => {
      active = false
    }
  }, [])

  return {
    context: {
      locale: session?.locale ?? 'vi',
      clanId: null,
      accessToken: session?.accessToken ?? null,
    },
    ready: session !== null,
  }
}
