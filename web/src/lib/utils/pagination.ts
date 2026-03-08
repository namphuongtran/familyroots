/** Encode a cursor string to be safe for URL query params */
export function encodeCursor(cursor: string): string {
  return encodeURIComponent(cursor)
}

/** Decode a cursor from a URL query param */
export function decodeCursor(encoded: string): string {
  return decodeURIComponent(encoded)
}

/**
 * Flatten TanStack infinite query pages into a single array.
 * Works with the backend's CursorPage<T> shape.
 */
export function flattenPages<T>(
  pages: Array<{ data: T[] }> | undefined,
): T[] {
  if (!pages) return []
  return pages.flatMap((page) => page.data)
}
