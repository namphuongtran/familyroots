import { expect, type APIRequestContext } from '@playwright/test'
import { mailCatcherOrigin } from './fixtures'

/**
 * The local stack's mail, read from Mailpit (`E2E_AUTH_MAIL_URL`). Its own file rather than
 * `fixtures.ts`, because `playwright.config.ts` imports that one and this one imports `expect`.
 *
 * `invitee-registers.auth.spec.ts` (#196) and `verify-email-confirm.auth.spec.ts` (#200) each
 * confirm a new address by the link the stack mailed, the way a person would, and
 * `reset-password.auth.spec.ts` (#201) resets a seeded user's password by one.
 */

/** The confirmation mail the local stack sent to `email`, polled until it arrives. */
export async function mailedConfirmation(
  request: APIRequestContext,
  email: string,
): Promise<{ subject: string; text: string; link: string }> {
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
): Promise<{ subject: string; text: string; link: string }> {
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
  const { Subject, Text } = (await message.json()) as { Subject: string; Text: string }
  // Under the stack's default template the link is GoTrue's own `/verify`. ADR-063's templates
  // (#202) replace it with a link to `/{locale}/verify-email/confirm` or `/{locale}/reset-password`.
  const link = Text.match(/https?:\/\/[^\s)]+\/auth\/v1\/verify\?[^\s)]+/)?.[0]
  if (!link) throw new Error(`the mail to ${email} carried no verify link:\n${Text}`)
  return { subject: Subject, text: Text, link }
}

/** Mailpit's search, newest first. */
async function search(request: APIRequestContext, email: string): Promise<{ ID: string }[]> {
  const response = await request.get(`${mailCatcherOrigin()}/api/v1/search`, {
    params: { query: `to:"${email}"` },
  })
  return ((await response.json()) as { messages: { ID: string }[] }).messages
}
