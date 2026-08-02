/**
 * Collapse concurrent invocations of an async operation onto one in-flight promise.
 *
 * When an access token expires, every request in flight 401s at the same moment.
 * Refreshing once per 401 would rotate the token N times and race over which
 * result is written last. One refresh, shared by all waiters.
 */
export function createSingleFlight<T>(operation: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null

  return () => {
    if (inFlight !== null) return inFlight
    // Clear on settle, not only on success: a transient failure must not latch
    // and block every future attempt.
    const attempt = operation().finally(() => {
      inFlight = null
    })
    inFlight = attempt
    return attempt
  }
}
