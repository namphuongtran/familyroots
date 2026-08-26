import { describe, expect, it } from 'vitest'
import { REDACTED, redactInvitationToken, redactInvitationTokensDeep } from './redact'

/**
 * These tests assert the **outcome** — the token is not in the string that comes
 * out — rather than the setting that the regex has a particular shape, per
 * `.claude/rules/seeds.md` § "A test pins an outcome, not a setting".
 *
 * `TOKEN` is a real-shaped value: `secrets.token_urlsafe(32)`
 * (`docs/contracts/rest-invitations-api.md:41`) produces 43 URL-safe base64
 * characters, which can include `-` and `_`. A test token of only letters would
 * pass while the pattern still broke on a real one.
 */
const TOKEN = 'Zx-9Qa_bC3dEfGhIjKlMnOpQrStUvWxYz0123456789'

describe('redactInvitationToken', () => {
  it('removes the token from the accept call path', () => {
    const before = `http://localhost:8000/api/v1/invitations/${TOKEN}/accept`

    const after = redactInvitationToken(before)

    expect(after).toBe(`http://localhost:8000/api/v1/invitations/${REDACTED}/accept`)
    expect(after).not.toContain(TOKEN)
  })

  it('removes the token from the browser route the invitation link lands on', () => {
    expect(redactInvitationToken(`/vi/invitations/${TOKEN}`)).toBe(`/vi/invitations/${REDACTED}`)
  })

  it('removes the token from a query string and fragment left on the URL', () => {
    const after = redactInvitationToken(`/vi/invitations/${TOKEN}?from=email#top`)

    expect(after).toBe(`/vi/invitations/${REDACTED}?from=email#top`)
  })

  /**
   * The exact message `apiFetch` builds at `shared/http/api-client.ts:119`. The
   * point of this case is that the sentence survives: a pattern that ran to the
   * end of the string would eat " failed" too and turn a readable error into a
   * stub.
   */
  it('cuts the token out of a NetworkError message without eating the sentence', () => {
    const after = redactInvitationToken(`request to /invitations/${TOKEN}/accept failed`)

    expect(after).toBe(`request to /invitations/${REDACTED}/accept failed`)
  })

  it('leaves the admin list route alone — there is no segment after it to redact', () => {
    const path = '/api/v1/clans/6f1c4f7e-0000-4000-8000-000000000001/invitations'

    expect(redactInvitationToken(path)).toBe(path)
  })

  it('leaves a string with no invitation path untouched', () => {
    expect(redactInvitationToken('/vi/login')).toBe('/vi/login')
    expect(redactInvitationToken('')).toBe('')
  })

  it('removes every occurrence, not only the first', () => {
    const after = redactInvitationToken(
      `/vi/invitations/${TOKEN} then /invitations/${TOKEN}/accept`,
    )

    expect(after).not.toContain(TOKEN)
  })
})

/**
 * A Sentry event, shaped the way the browser SDK actually builds one: the page URL
 * on `request.url`, a `fetch` breadcrumb and a navigation breadcrumb under
 * `breadcrumbs[].data`, the transaction name, and the thrown error's message under
 * `exception.values[].value`.
 *
 * This is the failure the scrubber exists to catch, so it is planted at every one
 * of those five places at once and the assertion is on the whole serialized event.
 * A per-field assertion would pass while a sixth field the SDK adds next year
 * carried the token through.
 */
function sentryLikeEvent() {
  return {
    event_id: 'abc',
    transaction: `/vi/invitations/${TOKEN}`,
    request: { url: `https://familyroots.example/vi/invitations/${TOKEN}`, method: 'GET' },
    breadcrumbs: [
      {
        category: 'fetch',
        data: {
          method: 'POST',
          url: `http://localhost:8000/api/v1/invitations/${TOKEN}/accept`,
          status_code: 403,
        },
      },
      {
        category: 'navigation',
        data: { from: `/vi/invitations/${TOKEN}`, to: '/vi/login' },
      },
    ],
    exception: {
      values: [{ type: 'NetworkError', value: `request to /invitations/${TOKEN}/accept failed` }],
    },
    tags: { locale: 'vi' },
    extra: { nested: { deeper: [`/invitations/${TOKEN}/accept`] } },
  }
}

describe('redactInvitationTokensDeep', () => {
  it('leaves no invitation token anywhere in a Sentry-shaped event', () => {
    const event = sentryLikeEvent()

    const scrubbed = redactInvitationTokensDeep(event)

    expect(JSON.stringify(scrubbed)).not.toContain(TOKEN)
  })

  it('planted at five separate places, every one of them comes back redacted', () => {
    const scrubbed = redactInvitationTokensDeep(sentryLikeEvent())

    expect(scrubbed.transaction).toBe(`/vi/invitations/${REDACTED}`)
    expect(scrubbed.request.url).toBe(`https://familyroots.example/vi/invitations/${REDACTED}`)
    expect(scrubbed.breadcrumbs[0].data.url).toBe(
      `http://localhost:8000/api/v1/invitations/${REDACTED}/accept`,
    )
    expect(scrubbed.breadcrumbs[1].data.from).toBe(`/vi/invitations/${REDACTED}`)
    expect(scrubbed.exception.values[0].value).toBe(
      `request to /invitations/${REDACTED}/accept failed`,
    )
  })

  it('reaches a token nested inside an array inside an object', () => {
    const scrubbed = redactInvitationTokensDeep(sentryLikeEvent())

    expect(scrubbed.extra.nested.deeper[0]).toBe(`/invitations/${REDACTED}/accept`)
  })

  it('returns the same object it was given, so a Sentry hook can return it directly', () => {
    const event = sentryLikeEvent()

    expect(redactInvitationTokensDeep(event)).toBe(event)
  })

  it('leaves every string that carries no token exactly as it was', () => {
    const scrubbed = redactInvitationTokensDeep(sentryLikeEvent())

    expect(scrubbed.event_id).toBe('abc')
    expect(scrubbed.tags.locale).toBe('vi')
    expect(scrubbed.breadcrumbs[1].data.to).toBe('/vi/login')
  })

  /** A Sentry event can hold a reference back to itself through `contexts`. */
  it('does not hang on a cyclic payload', () => {
    const payload: Record<string, unknown> = { url: `/vi/invitations/${TOKEN}` }
    payload.self = payload

    const scrubbed = redactInvitationTokensDeep(payload)

    expect(scrubbed.url).toBe(`/vi/invitations/${REDACTED}`)
  })

  it('survives the values a walker usually breaks on', () => {
    expect(redactInvitationTokensDeep(null)).toBeNull()
    expect(redactInvitationTokensDeep(undefined)).toBeUndefined()
    expect(redactInvitationTokensDeep(42)).toBe(42)
    // A bare string is not rewritten: a walker only replaces *properties*, and it
    // has nothing to write a new value into here. `redactInvitationToken` is the
    // function for a lone string, and the two callers that handle one use it.
    expect(redactInvitationTokensDeep(`/invitations/${TOKEN}`)).toBe(`/invitations/${TOKEN}`)
  })
})
