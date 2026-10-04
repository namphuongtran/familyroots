/**
 * The auth repository: fetch (`../api/auth-api`) → parse (`../model/session-dto`) → map to
 * domain (`@/domain/session/session`). It replaces the legacy `HttpAuthProfileRepository`,
 * which reached the backend through the axios client, and every envelope it reads goes through
 * `unwrapData`, so the four read sites that once took the whole body for the payload (#182,
 * `web/CLAUDE.md` "Three things found by looking at the harness") cannot recur.
 *
 * Every error leaves as the `ApiError` the transport built, `code` and `status` intact. A
 * screen branches on that `code`.
 */

import { unwrapData } from '@/shared/http/envelope'
import type { Session } from '@/domain/session/session'
import * as api from '../api/auth-api'
import type { AuthApiCallOptions } from '../api/auth-api'
import {
  clanSwitchResponseDtoSchema,
  messageDataDtoSchema,
  registerResponseDtoSchema,
  toMembership,
  toProfile,
  userClanMembershipDtoSchema,
  userProfileDtoSchema,
  type OnboardInput,
  type OnboardResult,
  type ProfileUpdate,
  type RegisterInput,
  type RegistrationReceived,
} from '../model/session-dto'

export type { AuthApiCallOptions }

/** The two reads that make a session, sent together. */
export async function fetchSession(options: AuthApiCallOptions): Promise<Session> {
  const [me, clans] = await Promise.all([api.getMe(options), api.listMyClans(options)])
  return {
    profile: unwrapData(me, (raw) => toProfile(userProfileDtoSchema.parse(raw))),
    memberships: unwrapData(clans, (raw) =>
      userClanMembershipDtoSchema.array().parse(raw).map(toMembership),
    ),
  }
}

/** Returns the clan id the backend confirmed, which is what the cookie gets. */
export async function selectClan(clanId: string, options: AuthApiCallOptions): Promise<string> {
  const body = await api.selectClan(clanId, options)
  return unwrapData(body, (raw) => clanSwitchResponseDtoSchema.parse(raw).clan_id)
}

export async function register(
  input: RegisterInput,
  options: AuthApiCallOptions,
): Promise<RegistrationReceived> {
  const body = await api.register(input, options)
  return unwrapData(body, (raw) => messageDataDtoSchema.parse(raw))
}

export async function onboard(
  input: OnboardInput,
  options: AuthApiCallOptions,
): Promise<OnboardResult> {
  const body = await api.onboard(input, options)
  return unwrapData(body, (raw) => {
    const dto = registerResponseDtoSchema.parse(raw)
    return { clanId: dto.clan_id, isApproved: dto.is_approved }
  })
}

export async function updateProfile(
  input: ProfileUpdate,
  options: AuthApiCallOptions,
): Promise<void> {
  const body = await api.updateMe(input, options)
  unwrapData(body, (raw) => messageDataDtoSchema.parse(raw))
}

export async function resendVerification(
  email: string,
  options: AuthApiCallOptions,
): Promise<void> {
  const body = await api.resendVerification(email, options)
  unwrapData(body, (raw) => messageDataDtoSchema.parse(raw))
}
