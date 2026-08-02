/**
 * The only module that knows the wire envelope. Everything above it sees
 * domain values and `Page<T>`.
 *
 * Contract (docs/contracts/README.md): every 2xx body is `{"data": ...}`;
 * cursor lists add `"meta": {cursor, has_more, limit}`. Cursors are opaque —
 * they are carried, never parsed.
 */

import { MalformedResponseError } from './errors'

export interface Page<T> {
  items: T[]
  /** Opaque. Pass back as the `cursor` query param; never inspect or build one. */
  cursor: string | null
  hasMore: boolean
  limit: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function unwrapData<T>(body: unknown, parse: (raw: unknown) => T): T {
  if (!isRecord(body) || !('data' in body)) {
    throw new MalformedResponseError('response body is not a {"data": ...} envelope')
  }
  return parse(body.data)
}

export function unwrapPage<T>(body: unknown, parseItem: (raw: unknown) => T): Page<T> {
  if (!isRecord(body) || !('data' in body)) {
    throw new MalformedResponseError('response body is not a {"data": ...} envelope')
  }
  if (!Array.isArray(body.data)) {
    throw new MalformedResponseError('paginated response data is not an array')
  }
  const meta = body.meta
  if (!isRecord(meta) || !('has_more' in meta) || !('limit' in meta)) {
    throw new MalformedResponseError(
      'paginated response is missing meta {cursor, has_more, limit} — ' +
        'a pre-envelope shape such as next_cursor is a contract violation',
    )
  }
  const cursor = meta.cursor
  return {
    items: body.data.map(parseItem),
    cursor: typeof cursor === 'string' ? cursor : null,
    hasMore: meta.has_more === true,
    limit: typeof meta.limit === 'number' ? meta.limit : body.data.length,
  }
}
