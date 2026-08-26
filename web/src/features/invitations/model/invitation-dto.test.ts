import { describe, expect, it } from 'vitest'
import {
  assertInvitationAcceptedDtoMatchesGenerated,
  invitationAcceptedDtoSchema,
  toAcceptedInvitation,
} from './invitation-dto'

/**
 * `docs/contracts/rest-invitations-api.md:95-98` gives the accept body verbatim:
 * `{ "data": { "clan_id": "...", "role": "...", "message": "..." } }`. This fixture
 * is that shape, with the `data` unwrapping left to `unwrapData` in the repository.
 */
function acceptedFixture(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    clan_id: '6f1c4f7e-0000-4000-8000-000000000001',
    role: 'viewer',
    message: 'Đã tham gia dòng họ',
    ...overrides,
  }
}

describe('invitationAcceptedDtoSchema', () => {
  it('accepts the contract body', () => {
    expect(invitationAcceptedDtoSchema.parse(acceptedFixture())).toEqual({
      clan_id: '6f1c4f7e-0000-4000-8000-000000000001',
      role: 'viewer',
      message: 'Đã tham gia dòng họ',
    })
  })

  it.each(['clan_id', 'role', 'message'])('rejects a body missing %s', (field) => {
    const body = acceptedFixture()
    delete body[field]

    expect(() => invitationAcceptedDtoSchema.parse(body)).toThrow()
  })

  it('rejects a null where the contract marks the field required and non-nullable', () => {
    expect(() => invitationAcceptedDtoSchema.parse(acceptedFixture({ clan_id: null }))).toThrow()
  })

  /**
   * The type-level guard cannot be asserted at runtime — it is
   * `pnpm type-check`'s job, and its body is nothing but `return dto`. What this
   * case pins is that the function is reachable and identity-preserving, so a
   * future edit that turns it into a mapper (and therefore stops being a pure type
   * assertion) is noticed.
   */
  it('the generated-type assert is the identity', () => {
    const dto = invitationAcceptedDtoSchema.parse(acceptedFixture())

    expect(assertInvitationAcceptedDtoMatchesGenerated(dto)).toBe(dto)
  })
})

describe('toAcceptedInvitation', () => {
  it('camelCases the two fields the screen needs', () => {
    const dto = invitationAcceptedDtoSchema.parse(acceptedFixture({ role: 'editor' }))

    expect(toAcceptedInvitation(dto)).toEqual({
      clanId: '6f1c4f7e-0000-4000-8000-000000000001',
      role: 'editor',
    })
  })

  /**
   * `message` is deliberately dropped. It is a backend-localised sentence
   * (`backend/app/api/v1/invitations.py:107` calls `t("invitation.accepted")`), and
   * `web/CLAUDE.md` says the UI branches on `code` and never on `message`. The
   * screen owns its own success copy in all four locale files, so carrying the
   * server's sentence would give the same fact two competing wordings.
   */
  it('drops the backend-worded message rather than carrying a second success copy', () => {
    const dto = invitationAcceptedDtoSchema.parse(acceptedFixture())

    expect(Object.keys(toAcceptedInvitation(dto)).sort()).toEqual(['clanId', 'role'])
  })

  it('passes a role it does not recognise through unchanged, rather than guessing', () => {
    const dto = invitationAcceptedDtoSchema.parse(acceptedFixture({ role: 'something_new' }))

    expect(toAcceptedInvitation(dto).role).toBe('something_new')
  })
})
