'use client'

/**
 * The submit on `/{locale}/forgot-password` (#201): `POST /auth/forgot-password`.
 *
 * The backend answers 200 for every address and swallows a provider failure (ADR-021), so a 200
 * says only that the request arrived, and the screen shows one message for it. A 429 is the
 * auth bucket's limit, read by its code (`docs/contracts/error-codes.md`). Anything else is a
 * transport failure with nothing more specific to say.
 */

import { useMutation } from '@tanstack/react-query'
import { ApiError } from '@/shared/http/errors'
import { forgotPassword } from '../server/auth-repository'
import { authCallOptions } from './auth-request-context'

/** The 429 the `/api/v1/auth` bucket answers with. */
const RATE_LIMITED_CODE = 'rate_limited'

export type PasswordResetRequestState = 'idle' | 'sending' | 'sent' | 'rate-limited' | 'failed'

export function useRequestPasswordReset(): {
  state: PasswordResetRequestState
  request: (email: string) => void
} {
  const { status, error, mutate } = useMutation({
    mutationFn: async (email: string) => forgotPassword(email, await authCallOptions()),
  })

  const state: PasswordResetRequestState =
    status === 'pending'
      ? 'sending'
      : status === 'success'
        ? 'sent'
        : status === 'error'
          ? error instanceof ApiError && error.code === RATE_LIMITED_CODE
            ? 'rate-limited'
            : 'failed'
          : 'idle'

  return { state, request: mutate }
}
