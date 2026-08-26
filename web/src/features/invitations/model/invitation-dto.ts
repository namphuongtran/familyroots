/**
 * The zod DTO for the one invitee-surface wire shape, constrained to
 * `src/generated/api-types.ts`, plus its mapper into `@/domain/invitation`.
 *
 * Same rule as `features/persons/model/person-dto.ts`, and for the same reason:
 * the schema mirrors `components["schemas"]["InvitationAcceptedResponse"]` field
 * for field, with its exact optionality and nullability, and
 * `assertInvitationAcceptedDtoMatchesGenerated` below is what turns a drift into a
 * `pnpm type-check` failure. That function's body is nothing but `return dto`, so
 * it compiles only while the inferred DTO type stays assignable to the generated
 * one. Widening a field here would break it too, which is the point.
 *
 * Only the accept response is modelled. The admin surface (create, list, revoke —
 * `docs/contracts/rest-invitations-api.md:23-58`) belongs to the admin invitation
 * screen, which is PR 7 in the `Owed` register of `docs/SEEDS.md` and is named
 * out of scope by seed S-084.
 */

import { z } from 'zod'
import type { components } from '@/generated/api-types'
import type { AcceptedInvitation } from '@/domain/invitation/invitation'

/**
 * Mirrors `components["schemas"]["InvitationAcceptedResponse"]`
 * (`src/generated/api-types.ts:2576-2585`): three required fields, none nullable.
 *
 * `role` is `z.string()` and not an enum. `backend/app/schemas/invitation.py:46`
 * types it `str` with no validator, so the generated type is `role: string`, and an
 * enum here would fail the assert below — see this file's header.
 */
export const invitationAcceptedDtoSchema = z.object({
  clan_id: z.string(),
  role: z.string(),
  message: z.string(),
})

export type InvitationAcceptedDto = z.infer<typeof invitationAcceptedDtoSchema>

export function assertInvitationAcceptedDtoMatchesGenerated(
  dto: InvitationAcceptedDto,
): components['schemas']['InvitationAcceptedResponse'] {
  return dto
}

/**
 * Wire `snake_case` into the domain's `camelCase`.
 *
 * `message` is dropped rather than carried. See the comment on
 * `AcceptedInvitation` in `@/domain/invitation/invitation`: it is a
 * backend-localised sentence, and this screen owns its own success copy in all
 * four locale files.
 */
export function toAcceptedInvitation(dto: InvitationAcceptedDto): AcceptedInvitation {
  return { clanId: dto.clan_id, role: dto.role }
}
