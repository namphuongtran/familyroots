import type { Metadata } from 'next'
import { InvitationAcceptScreen } from '@/features/invitations'

/**
 * The browser route an invitation link lands on: `/{locale}/invitations/{token}`.
 *
 * That is the shape the ADR-057 decision picked for the link an admin shares — a
 * browser URL on the web app's own origin, not the API path. See
 * `web/.env.example`'s `NEXT_PUBLIC_INVITE_LINK_ORIGIN` entry for the origin half
 * of it, and the finding recorded there about `accept_path`.
 *
 * A Server Component that renders one Client Component, and nothing else. It has to
 * be a server file to declare `metadata` below, and there is nothing for it to
 * fetch: the accept is a `POST` a person triggers (see
 * `features/invitations/hooks/use-accept-invitation`), so this route's `GET` reads
 * nothing and changes nothing.
 */

/**
 * **The one line on this page that is security, not presentation.**
 *
 * The token in this route's path is a bearer credential: it "is the only thing that
 * decides which clan the caller is granted a role in"
 * (`docs/contracts/rest-invitations-api.md:74`). Next.js renders this as
 * `<meta name="referrer" content="no-referrer">`, which sets the whole document's
 * referrer policy — so no request this page makes, and no link a visitor follows
 * from it, carries the token in a `Referer` header. The default policy
 * (`strict-origin-when-cross-origin`) would have sent the full path, token
 * included, on every *same-origin* navigation out of this page — for example the
 * "Sign in" link in every refusal state.
 *
 * Verified in a real browser rather than asserted:
 * `e2e/invitation-accept.spec.ts` follows that link and reads `document.referrer`
 * back as the empty string.
 */
export const metadata: Metadata = {
  referrer: 'no-referrer',
}

export default async function InvitationAcceptPage({
  params,
}: {
  params: Promise<{ locale: string; token: string }>
}) {
  const { locale, token } = await params

  return <InvitationAcceptScreen token={token} locale={locale} />
}
