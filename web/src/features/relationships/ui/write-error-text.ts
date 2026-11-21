/**
 * The text a failed relationship write shows when no field owns the error. Branches on the
 * error type and status, never on `message` text: a 403 is the editor's own sentence, any other
 * `ApiError` carries the backend's message, already localised from `Accept-Language`
 * (`shared/http/errors.ts`), and anything else is the generic retry line.
 */

import { ApiError } from '@/shared/http/errors'

export function writeErrorText(t: (key: string) => string, error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return t('forbidden')
    return error.message
  }
  return t('error_generic')
}
