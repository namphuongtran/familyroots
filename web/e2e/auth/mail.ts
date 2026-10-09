import { expect, type APIRequestContext } from '@playwright/test'
import { mailCatcherOrigin } from './fixtures'

/**
 * The local stack's mail, read from Mailpit (`E2E_AUTH_MAIL_URL`). Its own file rather than
 * `fixtures.ts`, because `playwright.config.ts` imports that one and this one imports `expect`.
 *
 * `invitee-registers.auth.spec.ts` (#196) and `verify-email-confirm.auth.spec.ts` (#200) each
 * confirm a new address by the link the stack mailed, the way a person would, and
 * `reset-password.auth.spec.ts` (#201) resets a seeded user's password by one.
 *
 * **The link is the one in the mail, as sent.** Since #202 the local stack renders the repository's
 * templates (`supabase/templates/`, ADR-063 § 1): `{{ .SiteURL }}/verify-email/confirm?token_hash=…&type=email`
 * and `{{ .SiteURL }}/reset-password?token_hash=…&type=recovery`. The Site URL is `SITE_URL_ORIGIN`,
 * where nothing listens, so a walk opens the link with `onOrigin`: the harness's origin in place of
 * the Site URL's, the path and the query unchanged.
 */

/** `supabase/config.toml` `[auth] site_url`: the origin of every link the local stack mails. */
export const SITE_URL_ORIGIN = 'http://127.0.0.1:3000'

/** `link` opened on `origin` instead of its own, with its path and query unchanged. */
export function onOrigin(link: string, origin: string | undefined): string {
  if (!origin) throw new Error(`no origin to open ${link} on: the auth project sets baseURL`)
  const { pathname, search } = new URL(link)
  return `${origin}${pathname}${search}`
}

/**
 * The mailed link's hash and query, once the link is read to be ADR-063 § 1's shape: on the Site
 * URL, at `path`, carrying `type` and a token hash, 56 hex characters (`{{ .TokenHash }}`).
 */
export function tokenHashLink(
  mail: Mail,
  path: string,
  type: 'email' | 'recovery',
): { tokenHash: string; search: string } {
  const link = new URL(mail.link)
  expect(`${link.origin}${link.pathname}`, mail.link).toBe(`${SITE_URL_ORIGIN}${path}`)
  expect(link.searchParams.get('type'), mail.link).toBe(type)
  const tokenHash = link.searchParams.get('token_hash') ?? ''
  expect(tokenHash, mail.link).toMatch(/^[0-9a-f]{56}$/)
  return { tokenHash, search: link.search }
}

/** A mail as Mailpit holds it. `bodyHtml` is the HTML from `<body` on, without the `<title>`. */
export interface Mail {
  subject: string
  text: string
  bodyHtml: string
  link: string
}

/** A template's Vietnamese heading and its English one. */
export interface Headings {
  vi: string
  en: string
}

/** Whether the Vietnamese heading comes before the English one, and both are there (ADR-063 § 7). */
export function readsVietnameseFirst(mail: Mail, { vi, en }: Headings): boolean {
  const at = mail.bodyHtml.indexOf(vi)
  return at >= 0 && at < mail.bodyHtml.indexOf(en)
}

/** The confirmation mail the local stack sent to `email`, polled until it arrives. */
export async function mailedConfirmation(request: APIRequestContext, email: string): Promise<Mail> {
  return newMail(request, email, new Set())
}

/**
 * The IDs of every mail Mailpit holds for `email` now. A seeded user's inbox keeps the mail of
 * earlier runs, so a walk that mails one reads these first and then waits for an ID not among
 * them (`reset-password.auth.spec.ts`, #201).
 */
export async function mailIdsFor(request: APIRequestContext, email: string): Promise<Set<string>> {
  return new Set((await search(request, email)).map(({ ID }) => ID))
}

/** The first mail to `email` whose ID is not in `seen`, polled until it arrives. */
export async function newMail(
  request: APIRequestContext,
  email: string,
  seen: ReadonlySet<string>,
): Promise<Mail> {
  const mail = mailCatcherOrigin()
  let id: string | undefined
  await expect
    .poll(
      async () => {
        id = (await search(request, email)).find(({ ID }) => !seen.has(ID))?.ID
        return id
      },
      { message: `no new mail reached ${email} in Mailpit at ${mail}`, timeout: 30_000 },
    )
    .toBeTruthy()
  const message = await request.get(`${mail}/api/v1/message/${id}`)
  const { Subject, Text, HTML } = (await message.json()) as {
    Subject: string
    Text: string
    HTML: string
  }
  // Read from the markup, not from Mailpit's text rendering of it. Each body links one URL, from
  // a button per language, so every `href` must be that one URL.
  const links = new Set(
    [...HTML.matchAll(/href="([^"]*)"/g)].map(([, href]) => href.replaceAll('&amp;', '&')),
  )
  if (links.size !== 1) {
    throw new Error(
      `the mail to ${email} links ${links.size} URLs, not one:\n${[...links].join('\n')}`,
    )
  }
  const [link] = links
  return { subject: Subject, text: Text, bodyHtml: HTML.slice(HTML.indexOf('<body')), link }
}

/** Mailpit's search, newest first. */
async function search(request: APIRequestContext, email: string): Promise<{ ID: string }[]> {
  const response = await request.get(`${mailCatcherOrigin()}/api/v1/search`, {
    params: { query: `to:"${email}"` },
  })
  return ((await response.json()) as { messages: { ID: string }[] }).messages
}
