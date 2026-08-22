'use client'

/**
 * The decision `web/CLAUDE.md` (S-030's own section, "Hooks... take a
 * `RequestContext` the caller passes in") left for whichever screen needed
 * one first: "almost certainly `useCurrentClanId()` plus the rest of the
 * session." This is that screen, and this is that decision.
 *
 * `useCurrentClanId()` (`@/shared/http/context.client`) is reactive — it
 * re-renders on a clan switch, which is what lets a TanStack Query key built
 * from the clan id refetch with no manual invalidation
 * (`shared/http/clan-switch.test.tsx` proves the underlying mechanism for a
 * plain `useQuery`). The access token has no equivalent reactive read —
 * nothing here subscribes to a Supabase auth-state change — so it is
 * resolved once, on mount, through `getClientRequestContext()`, and held in
 * state until this component unmounts. `enabled: false` on every persons
 * query until that resolve finishes, in `PersonsList`.
 *
 * **What this deliberately does not do.** It passes no `refreshAuth` to the
 * hooks it feeds. `web/CLAUDE.md`'s account of S-030 says building a real
 * browser `refreshAuth` — wiring `createSingleFlight`
 * (`shared/http/refresh.ts`) to a Supabase `refreshSession()` call — needs a
 * decision about where a browser-wide singleton like that lives, and "no
 * auth slice exists yet to own" it. That is still true here: this screen
 * needs a `RequestContext`, not an auth slice, and inventing the singleton
 * as a side effect of this hook would be exactly the kind of decision a seed
 * is supposed to isolate rather than smuggle into an unrelated one. A 401 on
 * this screen today surfaces as an error state with a retry button, not a
 * silent refresh-and-retry — a real gap, recorded here rather than papered
 * over silently.
 */

import { useEffect, useState } from 'react'
import { getClientRequestContext, useCurrentClanId } from '@/shared/http/context.client'
import type { RequestContext } from '@/shared/http/request-context'

interface Session {
  locale: RequestContext['locale']
  accessToken: RequestContext['accessToken']
}

export interface PersonsRequestContext {
  context: RequestContext
  /** False until the one-shot client session resolve has completed. */
  ready: boolean
}

export function usePersonsRequestContext(): PersonsRequestContext {
  const clanId = useCurrentClanId()
  const [session, setSession] = useState<Session | null>(null)

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
      clanId,
      accessToken: session?.accessToken ?? null,
    },
    ready: session !== null,
  }
}
