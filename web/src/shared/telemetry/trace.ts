/**
 * W3C Trace Context id generation (ADR-033).
 *
 * The backend's TraceContextMiddleware continues whatever we send here, so the
 * id in the browser console is the id in the API's JSON logs.
 */

const TRACEPARENT_RE = /^00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$/

function randomHex(byteLength: number): string {
  const bytes = new Uint8Array(byteLength)
  crypto.getRandomValues(bytes)
  let out = ''
  for (const byte of bytes) out += byte.toString(16).padStart(2, '0')
  // All-zero is invalid per spec. Astronomically unlikely, cheap to exclude.
  return /^0+$/.test(out) ? randomHex(byteLength) : out
}

/** Always sampled ('-01'): the backend decides retention, not the client. */
export function newTraceparent(): string {
  return `00-${randomHex(16)}-${randomHex(8)}-01`
}

export function traceIdOf(traceparent: string): string | null {
  const match = TRACEPARENT_RE.exec(traceparent.trim().toLowerCase())
  return match ? match[1] : null
}
