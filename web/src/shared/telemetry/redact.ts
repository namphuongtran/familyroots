/**
 * Keeping an invitation token out of telemetry.
 *
 * `docs/contracts/rest-invitations-api.md:74` says the invitation token "is the
 * only thing that decides which clan the caller is granted a role in". That makes
 * it a bearer credential, and it travels inside a URL path twice: in the browser
 * route `/{locale}/invitations/{token}` that seed S-084 added, and in the accept
 * call `POST /api/v1/invitations/{token}/accept` — the shape
 * `backend/app/application/invitation/handlers.py:65` hands to the admin who
 * shares the link.
 *
 * Telemetry copies URLs by default, so three real capture points existed in this
 * app before S-084, each read at source on 2026-08-26:
 *
 * 1. `web-vitals.tsx:19` logged `window.location.pathname` verbatim on every Web
 *    Vitals metric, through `logger` and on to `console`. That is the app's own
 *    log and its only analytics call.
 * 2. Sentry's browser SDK records a breadcrumb for every `fetch` and every router
 *    navigation, each carrying the URL, and puts the page URL on the event itself
 *    (`instrumentation-client.ts` calls `Sentry.init` with no scrubbing hooks).
 * 3. `apiFetch` builds `new NetworkError(`request to ${path} failed`)`
 *    (`shared/http/api-client.ts:119`), where `path` is the token-bearing path.
 *
 * The rule therefore lives here, once, and those three callers use it rather than
 * each inventing their own.
 *
 * **What the pattern matches, and the one false positive it accepts.** It rewrites
 * the path segment that follows a segment named `invitations`. That covers both
 * shapes above. It also rewrites `{invitation_id}` in the admin revoke route
 * `DELETE /clans/{clan_id}/invitations/{invitation_id}`
 * (`docs/contracts/rest-invitations-api.md:29`), which is not a credential. That
 * is accepted deliberately: an invitation id in a breadcrumb is worth nothing to
 * anybody reading telemetry, and a narrower pattern would have to know which
 * route it is looking at, which a free-text error message does not tell it.
 *
 * It does **not** match a token carried in a query parameter, because no code
 * here puts one there. If that ever changes, extend the pattern and its test
 * together.
 */

/** What replaces the token. Not the empty string: a reader should see that something was removed. */
export const REDACTED = '[redacted]'

/**
 * The segment after `invitations/`, stopping at the next path separator, query,
 * fragment, or whitespace — so a token embedded in a longer sentence (case 3
 * above) is cut out without swallowing the rest of the sentence.
 */
const INVITATION_TOKEN_SEGMENT = /(\/invitations\/)[^/?#\s'"]+/g

/** Replaces every invitation token in one string. Pure; safe on any string. */
export function redactInvitationToken(value: string): string {
  return value.replace(INVITATION_TOKEN_SEGMENT, `$1${REDACTED}`)
}

/**
 * How deep to walk a telemetry payload. A Sentry event nests about four levels
 * (`event.breadcrumbs[i].data.url`, `event.exception.values[i].value`), so eight
 * is generous while still bounding the work this does on every event.
 */
const MAX_DEPTH = 8

/**
 * Rewrites every string anywhere inside a telemetry payload, in place, and returns
 * the same object.
 *
 * In place, and generic over the whole payload rather than over a list of named
 * fields, because the field list is the SDK's to change: Sentry has moved the URL
 * between `event.request.url`, breadcrumb `data.url`, breadcrumb `data.from`/`to`,
 * `event.transaction`, and span attributes across versions. A scrubber that names
 * fields silently stops covering the one that moved, which is the failure mode
 * `.claude/rules/seeds.md` calls a check that passes because it scanned nothing.
 *
 * A write happens only when the string actually changes, so a payload with no
 * token is left untouched.
 */
export function redactInvitationTokensDeep<T>(payload: T): T {
  walk(payload, 0, new WeakSet<object>())
  return payload
}

function walk(node: unknown, depth: number, seen: WeakSet<object>): void {
  if (depth > MAX_DEPTH) return
  if (node === null || typeof node !== 'object') return
  if (seen.has(node)) return
  seen.add(node)

  if (Array.isArray(node)) {
    for (let index = 0; index < node.length; index += 1) {
      const item: unknown = node[index]
      if (typeof item === 'string') {
        const redacted = redactInvitationToken(item)
        if (redacted !== item) node[index] = redacted
      } else {
        walk(item, depth + 1, seen)
      }
    }
    return
  }

  const record = node as Record<string, unknown>
  for (const key of Object.keys(record)) {
    const item: unknown = record[key]
    if (typeof item === 'string') {
      const redacted = redactInvitationToken(item)
      if (redacted !== item) record[key] = redacted
    } else {
      walk(item, depth + 1, seen)
    }
  }
}
