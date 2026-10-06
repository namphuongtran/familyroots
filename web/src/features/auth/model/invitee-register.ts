/**
 * How the register form learns it was reached from an invitation (#196, ADR-058).
 *
 * The invitation page's signed-out state links to `/{locale}/register?from=invitation`. Reached
 * that way, the form asks for no clan and sends `POST /auth/register` with no `clan_action` and no
 * clan field, the body ADR-058 § 1 made the invitee's. The membership arrives later, from accept.
 *
 * **The marker carries no part of the token, and that is the point of it.** The token is a bearer
 * credential (`docs/contracts/rest-invitations-api.md:74`), and the invitation page decided, in
 * `d35decb`, to carry it nowhere: the person signs in, or registers, confirms and signs in, and then
 * opens the link again from the inbox or chat it arrived in. The marker says only where the
 * visitor came from. It cannot say which invitation.
 *
 * One builder and one reader, so the link the invitation page renders and the check the form makes
 * cannot drift apart.
 */

/** The query parameter, and the one value of it that marks the invitation entry. */
const MARKER_PARAM = 'from'
const MARKER_VALUE = 'invitation'

/** The create-an-account link on the invitation page's signed-out state. */
export function inviteeRegisterPath(locale: string): string {
  return `/${locale}/register?${new URLSearchParams({ [MARKER_PARAM]: MARKER_VALUE }).toString()}`
}

/** True when the register URL carries the marker `inviteeRegisterPath` writes. */
export function isInviteeRegister(searchParams: { get(name: string): string | null }): boolean {
  return searchParams.get(MARKER_PARAM) === MARKER_VALUE
}
