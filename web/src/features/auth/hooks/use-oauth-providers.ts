'use client'

/**
 * Which OAuth buttons the auth screens may offer (#290). The answer is the Supabase project's own
 * provider switch, `fetchEnabledOAuthProviders`, so turning Google on in the dashboard brings the
 * button back with no code change, and turning it off hides it.
 *
 * **It fails closed.** Until the read answers, and when it fails, every provider is off. A missing
 * button costs a person one click on the email form. A button for a provider that is off sends
 * them to Supabase's raw `400` JSON, which is what production showed on 2026-10-18.
 */

import { useQuery } from '@tanstack/react-query'
import { fetchEnabledOAuthProviders } from '../api/supabase-auth'
import { authKeys } from '../server/query-keys'

/** The switch changes in a dashboard, rarely. Five minutes spares a read on every page change. */
const OAUTH_PROVIDERS_STALE_TIME_MS = 5 * 60_000

export interface OAuthProviderAvailability {
  google: boolean
}

export function useOAuthProviders(): OAuthProviderAvailability {
  const { data } = useQuery({
    queryKey: authKeys.oauthProviders(),
    queryFn: fetchEnabledOAuthProviders,
    staleTime: OAUTH_PROVIDERS_STALE_TIME_MS,
    retry: false,
  })
  return { google: data?.includes('google') ?? false }
}
