/**
 * The sign-up confirmation link, as ADR-063 § 1 shapes it:
 * `{{ .SiteURL }}/verify-email/confirm?token_hash={{ .TokenHash }}&type=email`.
 *
 * Returns the hash a press may spend, or null for a link this page cannot spend: no hash, an
 * empty one, or a `type` other than `email`. `recovery` is the reset page's (#201), and the
 * deprecated `signup` is not what the template sends. Null shows the expired state, never a raw
 * error (spec § 7.1c), and sends nothing.
 */
export function confirmationTokenHash(query: Pick<URLSearchParams, 'get'>): string | null {
  const tokenHash = query.get('token_hash')
  if (!tokenHash || query.get('type') !== 'email') return null
  return tokenHash
}
