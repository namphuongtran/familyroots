import { describe, expect, it } from 'vitest'
import { callbackRedirects } from './redirects'

/**
 * #290: a failed OAuth return used to land on `/vi/login` whatever the reader's locale. The locale
 * now comes from the `next` `signInWithOAuth` sends, and a `next` that would leave the origin is
 * replaced by the default dashboard.
 */

describe('callbackRedirects', () => {
  it("sends a failure back to the login page in next's locale", () => {
    expect(callbackRedirects('/en/dashboard')).toEqual({
      success: '/en/dashboard',
      failure: '/en/login?error=auth_callback_failed',
    })
    expect(callbackRedirects('/zh/dashboard').failure).toBe('/zh/login?error=auth_callback_failed')
  })

  it('falls back to vi with no next, or a next whose first segment is no locale', () => {
    expect(callbackRedirects(null)).toEqual({
      success: '/vi/dashboard',
      failure: '/vi/login?error=auth_callback_failed',
    })
    expect(callbackRedirects('/xx/dashboard').failure).toBe('/vi/login?error=auth_callback_failed')
  })

  it.each(['@evil.example', '//evil.example', '/\\evil.example', 'https://evil.example', ''])(
    'never sends a success off the origin for next=%j',
    (next) => {
      expect(callbackRedirects(next).success).toBe('/vi/dashboard')
    },
  )
})
