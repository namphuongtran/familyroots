/**
 * Transport for the auth and membership routes this slice owns
 * (`docs/contracts/rest-auth-api.md`). Calls `apiFetch` and nothing else, and returns the raw
 * enveloped body. Parsing and mapping are `../server/auth-repository.ts`'s job, the same split
 * `features/persons/api/persons-api.ts` set.
 *
 * Sign-in, sign-out and OAuth are not here. They go to Supabase directly (ADR-061 § 7), so they
 * live in `./supabase-auth.ts`.
 */

import { apiFetch, type ApiFetchOptions } from '@/shared/http/api-client'
import type { OnboardInput, ProfileUpdate, RegisterInput } from '../model/session-dto'

export type AuthApiCallOptions = Pick<
  ApiFetchOptions,
  'context' | 'signal' | 'refreshAuth' | 'fetchImpl' | 'timeoutMs'
>

/** `GET /auth/me`: the profile, directly under `data`. */
export function getMe(options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch('/auth/me', options)
}

/** `PATCH /auth/me`. */
export function updateMe(body: ProfileUpdate, options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch('/auth/me', { ...options, method: 'PATCH', body })
}

/** `GET /me/clans`: the approved memberships, `{"data": [...]}`. */
export function listMyClans(options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch('/me/clans', options)
}

/** `POST /me/clans/{clan_id}/select`. */
export function selectClan(clanId: string, options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch(`/me/clans/${encodeURIComponent(clanId)}/select`, { ...options, method: 'POST' })
}

/** `POST /auth/register`: public, non-enumerating. */
export function register(body: RegisterInput, options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch('/auth/register', { ...options, method: 'POST', body })
}

/** `POST /auth/onboard`: attaches an already signed-in user to a clan. */
export function onboard(body: OnboardInput, options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch('/auth/onboard', { ...options, method: 'POST', body })
}

/** `POST /auth/resend-verification`: 200 always, non-enumerating. */
export function resendVerification(email: string, options: AuthApiCallOptions): Promise<unknown> {
  return apiFetch('/auth/resend-verification', { ...options, method: 'POST', body: { email } })
}
