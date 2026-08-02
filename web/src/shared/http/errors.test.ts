import { describe, expect, it } from 'vitest'
import { ApiError, parseErrorBody, policyActionFor } from './errors'

describe('parseErrorBody', () => {
  it('reads code, message, detail and trace id from the error envelope', () => {
    const error = parseErrorBody(
      {
        error: {
          code: 'person_not_found',
          message: 'Không tìm thấy người này',
          detail: { person_id: 'p-1' },
        },
      },
      404,
      '4bf92f3577b34da6a3ce929d0e0e4736',
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('person_not_found')
    expect(error.message).toBe('Không tìm thấy người này')
    expect(error.detail).toEqual({ person_id: 'p-1' })
    expect(error.status).toBe(404)
    expect(error.traceId).toBe('4bf92f3577b34da6a3ce929d0e0e4736')
  })

  it('defaults detail to an empty object', () => {
    const error = parseErrorBody({ error: { code: 'x', message: 'y' } }, 400, null)
    expect(error.detail).toEqual({})
  })

  it('synthesises a code when the body is not an error envelope at all', () => {
    // A proxy 502 or an HTML error page must still arrive as an ApiError with a
    // usable status, never as an unhandled parse crash.
    const error = parseErrorBody('<html>gateway</html>', 502, null)
    expect(error.code).toBe('unknown_error')
    expect(error.status).toBe(502)
  })
})

describe('policyActionFor', () => {
  it('maps every 403 code from the contract to its screen', () => {
    expect(policyActionFor('email_not_verified')).toBe('verify-email')
    expect(policyActionFor('account_deactivated')).toBe('account-deactivated')
    expect(policyActionFor('clan_suspended')).toBe('clan-blocked')
    expect(policyActionFor('clan_membership_required')).toBe('select-clan')
    expect(policyActionFor('no_approved_clan_membership')).toBe('onboarding')
  })

  it('denies quietly for any other policy code', () => {
    expect(policyActionFor('insufficient_permissions')).toBe('deny')
    expect(policyActionFor('some_future_code')).toBe('deny')
  })
})
