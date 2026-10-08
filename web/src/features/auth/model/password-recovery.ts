/**
 * The two refusals of a new password GoTrue names, read at the local stack on 2026-10-08:
 * `422 weak_password` below its minimum length, `422 same_password` for the current one. Any
 * other failure has nothing more specific to say.
 */
export type PasswordRefusal = 'weak' | 'same' | 'other'

export function passwordRefusalOf(code: string | null): PasswordRefusal {
  if (code === 'weak_password') return 'weak'
  if (code === 'same_password') return 'same'
  return 'other'
}
