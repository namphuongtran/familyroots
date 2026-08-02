/**
 * The error taxonomy every layer above the transport branches on.
 *
 * Rule from docs/contracts/error-codes.md: branch on `code`, never on `message`.
 * `message` is localized server-side from Accept-Language and its wording can
 * change at any time.
 */

export const INVALID_CURSOR_CODE = 'invalid_cursor'

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly detail: Record<string, unknown>
  readonly traceId: string | null

  constructor(args: {
    code: string
    message: string
    status: number
    detail?: Record<string, unknown>
    traceId?: string | null
  }) {
    super(args.message)
    this.name = 'ApiError'
    this.code = args.code
    this.status = args.status
    this.detail = args.detail ?? {}
    this.traceId = args.traceId ?? null
  }
}

/** The request never reached a response: offline, DNS failure, timeout, abort. */
export class NetworkError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = 'NetworkError'
  }
}

/** A 2xx arrived but did not match the frozen envelope — a contract violation. */
export class MalformedResponseError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'MalformedResponseError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function parseErrorBody(body: unknown, status: number, traceId: string | null): ApiError {
  if (isRecord(body) && isRecord(body.error)) {
    const { code, message, detail } = body.error
    return new ApiError({
      code: typeof code === 'string' ? code : 'unknown_error',
      message: typeof message === 'string' ? message : `Request failed with status ${status}`,
      status,
      detail: isRecord(detail) ? detail : {},
      traceId,
    })
  }
  // Not our envelope: an infrastructure error page, a proxy, a truncated body.
  return new ApiError({
    code: 'unknown_error',
    message: `Request failed with status ${status}`,
    status,
    traceId,
  })
}

/**
 * What the UI should do about a 403. Never refresh and never sign out here —
 * the credential is valid, policy is what denied the action.
 */
export type PolicyAction =
  'verify-email' | 'account-deactivated' | 'clan-blocked' | 'select-clan' | 'onboarding' | 'deny'

const POLICY_ACTIONS: Readonly<Record<string, PolicyAction>> = {
  email_not_verified: 'verify-email',
  account_deactivated: 'account-deactivated',
  clan_suspended: 'clan-blocked',
  clan_membership_required: 'select-clan',
  no_approved_clan_membership: 'onboarding',
}

export function policyActionFor(code: string): PolicyAction {
  return POLICY_ACTIONS[code] ?? 'deny'
}
