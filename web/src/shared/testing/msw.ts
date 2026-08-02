import { setupServer } from 'msw/node'

/**
 * Response builders that produce the **real** contract envelope.
 *
 * Tests must never hand-write a response object: a component that passes
 * against an invented shape proves nothing about production. Every handler in
 * every slice builds its body through these.
 */

export function envelope<T>(data: T): { data: T } {
  return { data }
}

export function pageEnvelope<T>(
  items: T[],
  meta: Partial<{ cursor: string | null; has_more: boolean; limit: number }> = {},
): { data: T[]; meta: { cursor: string | null; has_more: boolean; limit: number } } {
  return {
    data: items,
    meta: {
      cursor: meta.cursor ?? null,
      has_more: meta.has_more ?? false,
      limit: meta.limit ?? 20,
    },
  }
}

export function errorEnvelope(
  code: string,
  message: string,
  detail: Record<string, unknown> = {},
): { error: { code: string; message: string; detail: Record<string, unknown> } } {
  return { error: { code, message, detail } }
}

/** Slices register their own handlers with `server.use(...)` inside a test. */
export const server = setupServer()
