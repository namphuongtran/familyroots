import type { BrowserContext } from '@playwright/test'

/** The name of `@supabase/ssr`'s session cookie, or of one chunk of it; group 1 is the chunk. */
export const SESSION_COOKIE_NAME = /^sb-.+-auth-token(?:\.(\d+))?$/

/**
 * The access token in the browser's `sb-<ref>-auth-token` cookie. `@supabase/ssr` splits a long
 * value into `.0`, `.1`, … chunks and writes it as `base64-` and the base64url of the session.
 */
export async function browserAccessToken(context: BrowserContext): Promise<string> {
  const chunks = (await context.cookies())
    .map((cookie) => ({ cookie, match: SESSION_COOKIE_NAME.exec(cookie.name) }))
    .filter(({ match }) => match !== null)
    .sort((a, b) => Number(a.match?.[1] ?? 0) - Number(b.match?.[1] ?? 0))
  if (chunks.length === 0) throw new Error('the browser holds no Supabase session cookie')
  const value = decodeURIComponent(chunks.map(({ cookie }) => cookie.value).join(''))
  const json = value.startsWith('base64-')
    ? Buffer.from(value.slice('base64-'.length), 'base64url').toString('utf8')
    : value
  const { access_token } = JSON.parse(json) as { access_token?: string }
  if (!access_token) throw new Error('the Supabase session cookie carries no access token')
  return access_token
}
