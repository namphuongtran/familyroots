import { describe, expect, it } from 'vitest'
import { asClanRole, refusalFor, type InvitationRefusal } from './invitation'

/**
 * Every code below is read from `docs/contracts/error-codes.md:144-148` and
 * `docs/contracts/rest-invitations-api.md:66-70`, with the HTTP status each maps to
 * taken from `backend/app/core/exceptions.py:103-108` and the exception each
 * invariant raises in `backend/app/domain/invitation/entity.py:117-122`
 * (`ConflictError` → 409, `ForbiddenError` → 403). Checked at source 2026-08-26.
 */
const CONTRACT_CASES: ReadonlyArray<{
  code: string
  status: number
  expected: InvitationRefusal
  source: string
}> = [
  {
    code: 'invitation.email_mismatch',
    status: 403,
    expected: 'email-mismatch',
    source: 'error-codes.md:148, entity.py:122 raises ForbiddenError',
  },
  {
    code: 'invitation.expired',
    status: 409,
    expected: 'expired',
    source: 'error-codes.md:146, entity.py:120 raises ConflictError',
  },
  {
    code: 'invitation.not_pending',
    status: 409,
    expected: 'no-longer-open',
    source: 'error-codes.md:145, handlers.py:92 raises ConflictError',
  },
  {
    code: 'invitation.already_member',
    status: 409,
    expected: 'already-member',
    source: 'error-codes.md:147, handlers.py:98 raises ConflictError',
  },
  {
    code: 'invitation.not_found',
    status: 404,
    expected: 'not-found',
    source: 'error-codes.md:144, handlers.py:71 raises EntityNotFoundError',
  },
]

describe('refusalFor', () => {
  it.each(CONTRACT_CASES)(
    '$code ($status) is $expected — $source',
    ({ code, status, expected }) => {
      expect(refusalFor({ code, status })).toBe(expected)
    },
  )

  /**
   * The reason a code is read before a status. Three of the five contract codes
   * share status 409, so a mapping that looked at the status first could not tell
   * "expired", "already used or revoked", and "you are already in" apart — which is
   * the entire job of this page.
   */
  it('tells the three 409s apart, which a status-first mapping could not', () => {
    const byStatus409 = CONTRACT_CASES.filter((c) => c.status === 409).map((c) =>
      refusalFor({ code: c.code, status: c.status }),
    )

    expect(byStatus409).toEqual(['expired', 'no-longer-open', 'already-member'])
    expect(new Set(byStatus409).size).toBe(3)
  })

  it('reads 401 as sign-in-required, whatever the code on it is', () => {
    // `POST /invitations/{token}/accept` depends on `get_current_user`
    // (`backend/app/api/v1/invitations.py:96`) and the contract marks the row
    // `Auth | Yes` (`rest-invitations-api.md:62-64`), so a 401 here always means
    // "there is no usable session", never "this invitation is bad".
    expect(refusalFor({ code: 'unauthorized', status: 401 })).toBe('sign-in-required')
    expect(refusalFor({ code: '', status: 401 })).toBe('sign-in-required')
  })

  /**
   * **The failure this function exists to prevent.** A mapping with a permissive
   * default — anything unrecognised treated as fine — would let a backend that
   * grows a new invitation error code, or a proxy that returns an HTML 502, render
   * the "you have joined the clan" screen to somebody who joined nothing.
   *
   * Planted control, run on 2026-08-26 and recorded here rather than left as a
   * claim: changing the final `return 'unavailable'` in `refusalFor` to
   * `return 'already-member'` — the nearest thing to a success this type can
   * express — turned this test and "does not confuse a similar-looking code from
   * another surface" red, both reporting `expected 'already-member' to be
   * 'unavailable'`. The 401 case above stayed green, because it returns before the
   * fall-through, which is why the fall-through needs a case of its own. Restored
   * immediately afterwards.
   */
  it('never treats an unrecognised failure as anything but a refusal', () => {
    expect(refusalFor({ code: 'invitation.some_code_added_next_year', status: 409 })).toBe(
      'unavailable',
    )
    expect(refusalFor({ code: 'internal_error', status: 500 })).toBe('unavailable')
    // A NetworkError or a malformed body reaches this with nothing to branch on.
    expect(refusalFor({ code: '', status: 0 })).toBe('unavailable')
  })

  it('does not confuse a similar-looking code from another surface', () => {
    // `invitation.pending_exists` is the *admin* create conflict
    // (`error-codes.md:143`); it can never come back from accept, and if it did it
    // is not one of the five things this page knows how to say.
    expect(refusalFor({ code: 'invitation.pending_exists', status: 409 })).toBe('unavailable')
  })
})

describe('asClanRole', () => {
  it.each(['admin', 'editor', 'viewer'])('recognises %s', (role) => {
    expect(asClanRole(role)).toBe(role)
  })

  it('returns null for anything else, so a screen says nothing rather than printing a wire value', () => {
    // `backend/app/schemas/invitation.py:46` types the granted role `str` with no
    // validator, so this is a shape the contract genuinely permits.
    expect(asClanRole('super_admin')).toBeNull()
    expect(asClanRole('Admin')).toBeNull()
    expect(asClanRole('')).toBeNull()
  })
})
