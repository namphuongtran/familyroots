'use client'

/**
 * The press on `/{locale}/verify-email/confirm` (#200, ADR-063 § 2). A mutation, not a query: a
 * query runs on mount, and spending the token on mount is what § 2 forbids, because an email
 * scanner's fetch would spend it before the person clicks.
 *
 * Mutations do not retry here (`QueryClient`'s default), and a retry could only spend a token
 * twice. Any failure reads as expired: spec § 7.1c shows the expired state "rather than a raw
 * error", and the one failure Supabase names, `otp_expired`, means exactly that.
 */

import { useMutation } from '@tanstack/react-query'
import { verifyEmailLink } from '../api/supabase-auth'

export type ConfirmEmailState = 'ready' | 'verifying' | 'success' | 'expired'

export function useConfirmEmail(): {
  state: ConfirmEmailState
  confirm: (tokenHash: string) => void
} {
  const { status, mutate } = useMutation({ mutationFn: verifyEmailLink })

  const state: ConfirmEmailState =
    status === 'pending'
      ? 'verifying'
      : status === 'success'
        ? 'success'
        : status === 'error'
          ? 'expired'
          : 'ready'

  return { state, confirm: mutate }
}
