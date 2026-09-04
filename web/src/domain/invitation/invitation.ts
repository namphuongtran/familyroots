/**
 * What happens when somebody opens an invitation link, as a value rather than as
 * a branch inside a component.
 *
 * Plain TypeScript, same as the rest of `src/domain/`: no React, no zod, no
 * fetch. `domain-is-pure` and `domain-imports-only-domain`
 * (`web/.dependency-cruiser.cjs`) fail the build if this file reaches for any of
 * them.
 *
 * The invitation page. The reason the mapping lives here and not in the screen is that it
 * is the whole substance of the page: every one of the five refusals below is a
 * distinct thing to tell a relative, they come from a contract
 * (`docs/contracts/rest-invitations-api.md:64-78`), and a pure function is the
 * only version of them that can be tested without a browser.
 */

import type { ClanRole } from '@/domain/capability/capability'
import { CLAN_ROLES } from '@/domain/capability/capability'

/**
 * The successful outcome: `POST /invitations/{token}/accept` returned 200 and the
 * caller now holds `role` in `clanId`.
 *
 * `docs/contracts/rest-invitations-api.md:97` gives the response as
 * `{clan_id, role, message}`. `message` is not carried here on purpose. It arrives
 * already localised from the backend (`backend/app/api/v1/invitations.py:107`
 * calls `t("invitation.accepted")`), and `web/CLAUDE.md` — "The UI branches on the
 * error `code`, never on `message`" — makes a server-worded string something to
 * branch on at your peril. The screen has its own copy for this outcome in all four
 * locale files, so the server's sentence would only be a second, competing wording
 * of the same fact.
 */
export interface AcceptedInvitation {
  readonly clanId: string
  /**
   * The granted role, as the wire sent it. Deliberately `string` and not
   * `ClanRole`: `backend/app/schemas/invitation.py:46` types it `str` and the
   * generated OpenAPI type says `role: string`, so narrowing it here would be a
   * claim the contract does not make. Use `asClanRole` below to decide whether it
   * is one of the three names a screen has a label for.
   */
  readonly role: string
}

/**
 * `role` narrowed to one of the three clan roles, or `null` when the backend sent
 * something else. A screen that cannot name a role should say nothing about it
 * rather than print a raw wire value at a relative.
 */
export function asClanRole(role: string): ClanRole | null {
  return CLAN_ROLES.includes(role as ClanRole) ? (role as ClanRole) : null
}

/**
 * Every way opening an invitation link can fail, one per thing the page has to
 * say. Each maps to an error code in
 * `docs/contracts/rest-invitations-api.md:66-70` and
 * `docs/contracts/error-codes.md:144-148`, except the last two.
 */
export type InvitationRefusal =
  /** `invitation.email_mismatch`, 403. The signed-in account is not the invited one. */
  | 'email-mismatch'
  /** `invitation.expired`, 409. The link timed out; the admin has to send a new one. */
  | 'expired'
  /** `invitation.not_pending`, 409. Already accepted, or revoked by the admin. */
  | 'no-longer-open'
  /** `invitation.already_member`, 409. Nothing to do — the caller is in the clan already. */
  | 'already-member'
  /** `invitation.not_found`, 404. No invitation carries this token. */
  | 'not-found'
  /** 401. Accept needs a session (`docs/contracts/rest-invitations-api.md:64`, Auth = Yes). */
  | 'sign-in-required'
  /** Anything else: a 500, a timeout, an offline browser, a code this build has never heard of. */
  | 'unavailable'

/**
 * One entry per invitation error code the contract defines for accept. The keys are
 * the codes, verbatim, because `web/CLAUDE.md` says the UI branches on `code` and
 * never on `message` — `message` arrives already localised and its wording can
 * change at any time.
 */
const REFUSAL_BY_CODE: Readonly<Record<string, InvitationRefusal>> = {
  'invitation.email_mismatch': 'email-mismatch',
  'invitation.expired': 'expired',
  'invitation.not_pending': 'no-longer-open',
  'invitation.already_member': 'already-member',
  'invitation.not_found': 'not-found',
}

/**
 * Which refusal a failed accept was.
 *
 * **A code always wins over a status**, because the code is the thing the contract
 * pins and the status is shared by unrelated failures: `invitation.expired`,
 * `invitation.not_pending` and `invitation.already_member` are all 409
 * (`docs/contracts/error-codes.md:145-147`), and telling them apart is the point
 * of the page.
 *
 * **There is deliberately no path from here to a success.** The only thing that may
 * produce `AcceptedInvitation` is a 200 from the backend. An unrecognised code
 * lands on `'unavailable'` — a refusal — so a backend that grows a new invitation
 * error code makes this page say "we could not do this", never "you are in".
 * `invitation.test.ts` plants exactly that mutation and watches the
 * email-mismatch case go red.
 */
export function refusalFor(failure: { code: string; status: number }): InvitationRefusal {
  const byCode = REFUSAL_BY_CODE[failure.code]
  if (byCode !== undefined) return byCode
  if (failure.status === 401) return 'sign-in-required'
  return 'unavailable'
}
