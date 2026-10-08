'use client'

/**
 * The submit on `/{locale}/reset-password` (#201, ADR-063 § 2). A mutation, not a query, for
 * `useConfirmEmail`'s reason: a query runs on mount, and an email scanner's fetch would spend the
 * token before the person types anything.
 *
 * **One submit spends the token, and only once.** The first submit calls `verifyOtp`, then
 * `updateUser`. If `updateUser` is refused, the session the verify saved still holds, so the
 * next submit calls `updateUser` only: a second verify of the spent token would answer 403 and
 * turn a weak-password retry into the expired state. `verified` remembers the spend for the life
 * of the page.
 *
 * **One submit at a time.** TanStack Query reports a pending mutation on a later task, so a
 * second submit that lands first would run the whole sequence again. The ref holds it
 * synchronously, as `useConfirmEmail`'s does.
 *
 * Any failure of the verify reads as expired, as on the confirmation page. A refused update
 * stays on the form with the refusal named.
 */

import { useCallback, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { supabaseErrorCode, updatePassword, verifyRecoveryLink } from '../api/supabase-auth'
import { passwordRefusalOf, type PasswordRefusal } from '../model/password-recovery'

export type ResetPasswordState =
  | { kind: 'ready'; refusal: PasswordRefusal | null }
  | { kind: 'saving' }
  | { kind: 'success' }
  | { kind: 'expired' }

/** The verify was refused: the link is spent, expired or unknown. */
class RecoveryLinkRefused extends Error {
  constructor(cause: unknown) {
    super('the recovery link was refused', { cause })
    this.name = 'RecoveryLinkRefused'
  }
}

export function useResetPassword(): {
  state: ResetPasswordState
  submit: (tokenHash: string, password: string) => void
} {
  const verified = useRef(false)
  const inFlight = useRef(false)
  const { status, error, mutate } = useMutation({
    mutationFn: async ({ tokenHash, password }: { tokenHash: string; password: string }) => {
      if (!verified.current) {
        try {
          await verifyRecoveryLink(tokenHash)
        } catch (cause) {
          throw new RecoveryLinkRefused(cause)
        }
        verified.current = true
      }
      await updatePassword(password)
    },
    onSettled: () => {
      inFlight.current = false
    },
  })

  const submit = useCallback(
    (tokenHash: string, password: string) => {
      if (inFlight.current) return
      inFlight.current = true
      mutate({ tokenHash, password })
    },
    [mutate],
  )

  const state: ResetPasswordState =
    status === 'pending'
      ? { kind: 'saving' }
      : status === 'success'
        ? { kind: 'success' }
        : status === 'error'
          ? error instanceof RecoveryLinkRefused
            ? { kind: 'expired' }
            : { kind: 'ready', refusal: passwordRefusalOf(supabaseErrorCode(error)) }
          : { kind: 'ready', refusal: null }

  return { state, submit }
}
