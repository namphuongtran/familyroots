import { expect, type APIRequestContext } from '@playwright/test'
import { mailCatcherOrigin } from './fixtures'

/**
 * The local stack's mail, read from Mailpit (`E2E_AUTH_MAIL_URL`). Its own file rather than
 * `fixtures.ts`, because `playwright.config.ts` imports that one and this one imports `expect`.
 *
 * `invitee-registers.auth.spec.ts` (#196) and `verify-email-confirm.auth.spec.ts` (#200) each
 * confirm a new address by the link the stack mailed, the way a person would.
 */

/** The confirmation mail the local stack sent to `email`, polled until it arrives. */
export async function mailedConfirmation(
  request: APIRequestContext,
  email: string,
): Promise<{ subject: string; text: string; link: string }> {
  const mail = mailCatcherOrigin()
  let id: string | undefined
  await expect
    .poll(
      async () => {
        const search = await request.get(`${mail}/api/v1/search`, {
          params: { query: `to:"${email}"` },
        })
        const body = (await search.json()) as { messages: { ID: string }[] }
        id = body.messages[0]?.ID
        return id
      },
      { message: `no mail reached ${email} in Mailpit at ${mail}`, timeout: 30_000 },
    )
    .toBeTruthy()
  const message = await request.get(`${mail}/api/v1/message/${id}`)
  const { Subject, Text } = (await message.json()) as { Subject: string; Text: string }
  // Under the stack's default template the link is GoTrue's own `/verify`. ADR-063's template
  // (#202) replaces it with a link to `/{locale}/verify-email/confirm`.
  const link = Text.match(/https?:\/\/[^\s)]+\/auth\/v1\/verify\?[^\s)]+/)?.[0]
  if (!link) throw new Error(`the mail to ${email} carried no confirmation link:\n${Text}`)
  return { subject: Subject, text: Text, link }
}

/** The link alone, for a walk that only follows it. */
export async function mailedConfirmationLink(
  request: APIRequestContext,
  email: string,
): Promise<string> {
  return (await mailedConfirmation(request, email)).link
}
