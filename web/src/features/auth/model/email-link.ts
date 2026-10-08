/**
 * The two auth email links, as ADR-063 § 1 shapes them:
 *
 * - `{{ .SiteURL }}/verify-email/confirm?token_hash={{ .TokenHash }}&type=email` (#200)
 * - `{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}&type=recovery` (#201)
 *
 * Returns the hash a user action may spend, or null for a link the page cannot spend: no hash,
 * an empty one, or a `type` other than the page's own. The deprecated `signup` is not what the
 * template sends. Null shows the expired state and sends nothing (§ 2, spec § 7.1c).
 */
export type EmailLinkType = 'email' | 'recovery'

export function emailLinkTokenHash(
  query: Pick<URLSearchParams, 'get'>,
  type: EmailLinkType,
): string | null {
  const tokenHash = query.get('token_hash')
  if (!tokenHash || query.get('type') !== type) return null
  return tokenHash
}
