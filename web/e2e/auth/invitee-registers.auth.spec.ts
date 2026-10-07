import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import type { components } from '../../src/generated/api-types'
import { authStackInputs, SEEDED_PASSWORD, SEEDED_USERS } from './fixtures'
import { mailedConfirmation } from './mail'

/**
 * #196, ADR-058. A person with no account opens an invitation link, creates an account from it,
 * confirms the address, signs in, opens the link again and joins. Before #196 the page's
 * signed-out state offered one action, a link to `/vi/login`, so this person had no way in.
 *
 * **One test, in steps, because the steps share one person.** Each step depends on the one before:
 * the account the register step creates is the one the mail confirms and the sign-in uses.
 *
 * **What it reads at the end is the membership, not the page.** `GET /me/clans` as the new user
 * must answer exactly one approved membership, in the inviting clan, with the invited role. The
 * invitation names `editor`, which no other path in this walk could grant: a join request is a
 * pending `viewer`, and a clanless account holds nothing.
 *
 * **The token stays in one place, and the walk checks it as it goes.** Every request URL, every
 * `Referer` header and every document URL is recorded from the first navigation on, and
 * `localStorage`, `sessionStorage` and `document.cookie` are read on the register page and again
 * after sign-in. The token may appear only in the invitation page's own URL and in the accept
 * request's path. The page decided in `d35decb` to carry the token nowhere, and #196 extended
 * that to registration; `InvitationAcceptScreen.tsx`'s header holds the reasons.
 *
 * **The confirmation is the way a person does it.** The backend creates the identity unconfirmed
 * (`email_confirm: False`, `supabase_identity_provider.py`), so `enable_confirmations = false` in
 * `supabase/config.toml` does not apply, and GoTrue refuses the password grant with
 * `email_not_confirmed` until the link is followed. The local stack mails that link to Mailpit
 * (`E2E_AUTH_MAIL_URL`). Under the stack's default template the link is GoTrue's own `/verify`,
 * which confirms on the request and redirects to `site_url`, `http://127.0.0.1:3000`, where
 * nothing listens. So the link is requested rather than opened in the page, and its `303` and
 * `Location` are read. When ADR-063's template (#203) reaches the local stack, the link lands on
 * `/{locale}/verify-email/confirm` (#200) and this step presses its button instead.
 *
 * **Budget.** `/api/v1/auth` and `/api/v1/invitations` share one bucket per IP, 20 requests per
 * 60 seconds unless the backend sets `RATE_LIMIT_AUTH_MAX_REQUESTS`. The harness's backend sets
 * 1000 since #226, because a full run of this suite spends 28 in under a minute from one address
 * (`web/CLAUDE.md`, "Budget the requests"). The walk counts what it spent and attaches the count;
 * measured on 2026-10-06, see the commit that added this file. The admin's requests go to
 * `/api/v1/clans` and `/api/v1/me`, which spend nothing.
 *
 * **What it leaves behind.** The invitation is accepted, so it is no longer pending. The new
 * user's membership is removed afterwards through the admin route, so the seeded clan does not
 * collect members. The identity stays in the local stack's `auth.users`: the harness holds no
 * service-role key to delete it, and each run uses a fresh address.
 */

/** `messages/vi.json`. */
const COPY = {
  signInRequired: 'Hãy đăng nhập trước',
  createAccount: 'Tạo tài khoản',
  fullName: 'Họ và tên',
  email: 'Email',
  password: 'Mật khẩu',
  register: 'Đăng ký',
  inviteeSuccessNext: 'Sau khi xác nhận email và đăng nhập, hãy mở lại liên kết lời mời của bạn.',
  signIn: 'Đăng nhập',
  accept: 'Tham gia dòng họ',
  accepted: 'Bạn đã tham gia dòng họ',
} as const

/** `backend/app/i18n/vi.json`, `auth.registration_received`: the 201 body the success screen shows. */
const REGISTRATION_RECEIVED = 'Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp theo'

const INVITED_ROLE = 'editor'
const INVITEE_PASSWORD = 'invitee-password-196'

/**
 * A first visit to a route on a cold `next dev` compiles it, about 18 s (web/CLAUDE.md, "The
 * authenticated e2e harness"), and a run starts its own server. Each route's first reading waits
 * this long; later readings take the default.
 */
const FIRST_VISIT = { timeout: 45_000 }

type CreatedInvitation = components['schemas']['InvitationCreatedResponse']
type ClanMembership = components['schemas']['UserClanMembership']

async function passwordGrant(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<{ access_token: string; user: { id: string } }> {
  const response = await request.post(
    `${authStackInputs().supabaseUrl}/auth/v1/token?grant_type=password`,
    { headers: { apikey: authStackInputs().supabaseAnonKey }, data: { email, password } },
  )
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()) as { access_token: string; user: { id: string } }
}

async function myClans(request: APIRequestContext, accessToken: string): Promise<ClanMembership[]> {
  const response = await request.get(`${authStackInputs().apiOrigin}/api/v1/me/clans`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  expect(response.status(), await response.text()).toBe(200)
  return ((await response.json()) as { data: ClanMembership[] }).data
}

/** Everything the browser asked for, and every document it showed, from the first navigation on. */
function recordTheWalk(page: Page) {
  const requests: { method: string; url: string; referer: string | undefined }[] = []
  const documents: string[] = []
  page.on('request', (request) => {
    requests.push({
      method: request.method(),
      url: request.url(),
      referer: request.headers()['referer'],
    })
  })
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) documents.push(frame.url())
  })
  return { requests, documents }
}

/**
 * **The walk's web origin is the invite link's, not the project's `baseURL`.** The backend builds
 * the link on `INVITE_LINK_ORIGIN`. On a laptop that is the harness's own origin, but the image e2e
 * job (#193) cannot use a loopback value, so its links open on `http://familyroots-web.test:3102`,
 * the same server under another name. A session cookie belongs to one host, so every page of the
 * walk opens on the link's origin, and the token's home is read there too. Read against
 * `baseURL`, the job's first run past its image pull (2026-10-07) named the invitation page's own
 * URL as a leak, and a sign-in on `127.0.0.1` left the reopened link signed out.
 */
function walkOrigin(invitation: CreatedInvitation): string {
  return new URL(invitation.invite_url).origin
}

/** Where the token is allowed: this page's own URL, and the accept request's path. */
function isAllowedHome(url: string, token: string, web: string): boolean {
  const { origin, pathname } = new URL(url)
  return (
    (origin === web && pathname === `/vi/invitations/${token}`) ||
    (origin === authStackInputs().apiOrigin && pathname === `/api/v1/invitations/${token}/accept`)
  )
}

/**
 * **The one request the check sets aside, by name, and why.** Measured 2026-10-06: on the click to
 * the register page, `next dev`'s overlay shows its compile indicator and fetches its own font,
 * `GET /__nextjs_font/geist-latin.woff2`, with the invitation URL as `Referer`, although the
 * document's policy is `no-referrer`. In the same click the app's RSC fetch and its chunk loads
 * carried no `Referer`. The route is the dev overlay's: only `next dev`'s hot reloaders mount
 * `getDevOverlayFontMiddleware` (`next/dist/server/dev/hot-reloader-turbopack.js`), so a production
 * build neither serves it nor renders the overlay that asks for it. Read against `next start` the
 * same day, the same click made 25 requests, none to `/__nextjs_font/` and none with the token in
 * its `Referer`. It is same-origin. The check
 * reports what it set aside in the test's annotations, so a reader sees it, and sets aside nothing
 * else: a request to any other path is still named.
 */
function isDevOverlayFont(url: string, web: string): boolean {
  const { origin, pathname } = new URL(url)
  return origin === web && pathname === '/__nextjs_font/geist-latin.woff2'
}

/** Every place the token showed up outside its two homes, each named. */
function tokenOutsideItsHome(
  walk: ReturnType<typeof recordTheWalk>,
  token: string,
  web: string,
): { found: string[]; setAside: string[] } {
  const found: string[] = []
  const setAside: string[] = []
  for (const { method, url, referer } of walk.requests) {
    if (url.includes(token) && !isAllowedHome(url, token, web)) {
      found.push(`request ${method} ${url}`)
    }
    if (referer?.includes(token)) {
      const entry = `Referer ${referer} on ${method} ${url}`
      if (isDevOverlayFont(url, web)) setAside.push(entry)
      else found.push(entry)
    }
  }
  for (const url of walk.documents) {
    if (url.includes(token) && !isAllowedHome(url, token, web)) found.push(`document ${url}`)
  }
  return { found, setAside }
}

function expectTokenInItsHome(
  walk: ReturnType<typeof recordTheWalk>,
  token: string,
  web: string,
  through: string,
): void {
  const { found, setAside } = tokenOutsideItsHome(walk, token, web)
  if (setAside.length > 0) {
    test.info().annotations.push({
      type: `set aside through ${through}: the next dev overlay font`,
      description: setAside.map((entry) => entry.replaceAll(token, '<token>')).join('; '),
    })
  }
  expect(found).toEqual([])
}

/** `localStorage`, `sessionStorage` and `document.cookie`, as one string per store. */
async function browserStores(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => {
    const dump = (storage: Storage) =>
      Array.from({ length: storage.length }, (_, index) => {
        const key = storage.key(index) ?? ''
        return `${key}=${storage.getItem(key) ?? ''}`
      }).join('\n')
    return {
      localStorage: dump(window.localStorage),
      sessionStorage: dump(window.sessionStorage),
      'document.cookie': document.cookie,
    }
  })
}

async function expectStoresFreeOf(page: Page, token: string, where: string): Promise<void> {
  const stores = await browserStores(page)
  const holding = Object.entries(stores)
    .filter(([, value]) => value.includes(token))
    .map(([name]) => name)
  expect(holding, `the token was written to ${holding.join(', ')} ${where}`).toEqual([])
}

test.describe('a person with no account joins through an invitation link', () => {
  // No session: the person who opens the link has never signed in.
  test.use({ storageState: { cookies: [], origins: [] } })
  // Four cold routes at `FIRST_VISIT` each, and a mail to wait for.
  test.setTimeout(300_000)

  let invitation: CreatedInvitation
  let clanId: string
  let inviteeEmail: string
  let adminHeaders: Record<string, string>
  let admin: APIRequestContext
  let inviteeUserId: string | undefined

  test.beforeAll(async ({ playwright }) => {
    admin = await playwright.request.newContext()
    const { access_token } = await passwordGrant(admin, SEEDED_USERS.admin.email, SEEDED_PASSWORD)
    const clan = (await myClans(admin, access_token)).find(
      (row) => row.clan_slug === SEEDED_USERS.admin.clanSlug,
    )
    if (!clan)
      throw new Error(`the seeded admin holds no membership in ${SEEDED_USERS.admin.clanSlug}`)
    clanId = clan.clan_id
    adminHeaders = {
      Authorization: `Bearer ${access_token}`,
      'X-Current-Clan-Id': clanId,
      'Accept-Language': 'vi',
    }

    // A fresh address: a reused one answers `invitation.pending_exists`.
    inviteeEmail = `invitee-196-${crypto.randomUUID()}@familyroots.example.com`
    const response = await admin.post(
      `${authStackInputs().apiOrigin}/api/v1/clans/${clanId}/invitations`,
      { headers: adminHeaders, data: { email: inviteeEmail, role: INVITED_ROLE } },
    )
    expect(response.status(), await response.text()).toBe(201)
    invitation = ((await response.json()) as { data: CreatedInvitation }).data
  })

  test.afterAll(async () => {
    const api = `${authStackInputs().apiOrigin}/api/v1/clans`
    if (inviteeUserId) {
      // Accepted: take the membership back out of the seeded clan.
      const removed = await admin.delete(`${api}/me/users/${inviteeUserId}`, {
        headers: adminHeaders,
      })
      expect(removed.status(), await removed.text()).toBe(200)
    } else if (invitation) {
      // Not accepted: revoke it, so the seeded clan does not collect pending invitations.
      await admin.delete(`${api}/${clanId}/invitations/${invitation.id}`, { headers: adminHeaders })
    }
    await admin.dispose()
  })

  test('registers with no clan, confirms, signs in, opens the link again and holds the invited role', async ({
    page,
    request,
  }) => {
    const token = invitation.token
    const web = walkOrigin(invitation)
    const walk = recordTheWalk(page)

    await test.step('opens the invitation link with no session', async () => {
      await page.goto(invitation.invite_url)
      await expect(page.getByRole('heading', { name: COPY.signInRequired })).toBeVisible(
        FIRST_VISIT,
      )
    })

    await test.step('follows create an account', async () => {
      // Named in the failure, so a page that offers only sign-in says so rather than timing out.
      const offered = await page
        .getByRole('link')
        .evaluateAll((links) =>
          links.map((link) => `"${link.textContent?.trim()}" -> ${link.getAttribute('href')}`),
        )
      const createAccount = page.getByRole('link', { name: COPY.createAccount })
      await expect(createAccount, `the signed-out state offers ${offered.join(', ')}`).toBeVisible()
      await createAccount.click()
      await page.waitForURL((url) => url.pathname === '/vi/register', FIRST_VISIT)
      await expect(page.getByLabel(COPY.fullName)).toBeVisible(FIRST_VISIT)
      await expectStoresFreeOf(page, token, 'on the register page')
    })

    await test.step('registers with the invited address and no clan', async () => {
      await page.getByLabel(COPY.fullName).fill('Người Được Mời 196')
      await page.getByLabel(COPY.email, { exact: true }).fill(inviteeEmail)
      await page.getByLabel(COPY.password).fill(INVITEE_PASSWORD)
      await page.getByRole('button', { name: COPY.register, exact: true }).click()

      await expect(page.getByText(REGISTRATION_RECEIVED)).toBeVisible(FIRST_VISIT)
      await expect(page.getByText(COPY.inviteeSuccessNext)).toBeVisible()
    })

    await test.step('the token stayed in one place, through the success screen', async () => {
      expectTokenInItsHome(walk, token, web, 'the success screen')
    })

    await test.step('confirms the address by the link the local stack mailed', async () => {
      const { link } = await mailedConfirmation(request, inviteeEmail)
      const followed = await request.get(link, { maxRedirects: 0 })
      expect(followed.status()).toBe(303)
      // GoTrue reports a failed verification in the redirect's fragment, `#error=…`.
      expect(followed.headers()['location']).not.toContain('error')
    })

    await test.step('signs in at /vi/login', async () => {
      await page.goto(`${web}/vi/login`)
      await expect(page.getByLabel(COPY.email, { exact: true })).toBeEditable(FIRST_VISIT)
      await page.getByLabel(COPY.email, { exact: true }).fill(inviteeEmail)
      await page.getByLabel(COPY.password).fill(INVITEE_PASSWORD)
      await page.getByRole('button', { name: COPY.signIn, exact: true }).click()
      // A clanless account lands where `landingPath` sends `needs-onboarding`.
      await page.waitForURL((url) => url.pathname === '/vi/register', FIRST_VISIT)
      await expectStoresFreeOf(page, token, 'after sign-in')
    })

    await test.step('opens the invitation link again and joins', async () => {
      await page.goto(invitation.invite_url)
      const accept = page.getByRole('button', { name: COPY.accept })
      await expect(accept).toBeEnabled(FIRST_VISIT)
      await accept.click()
      await expect(page.getByRole('heading', { name: COPY.accepted })).toBeVisible()
    })

    await test.step('the token stayed in one place, through the accept', async () => {
      expectTokenInItsHome(walk, token, web, 'the accept')
      expect(walk.requests.map((r) => `${r.method} ${r.url}`)).toContain(
        `POST ${authStackInputs().apiOrigin}/api/v1/invitations/${token}/accept`,
      )
    })

    await test.step('GET /me/clans holds one approved membership, the invited one', async () => {
      const invitee = await passwordGrant(request, inviteeEmail, INVITEE_PASSWORD)
      inviteeUserId = invitee.user.id
      // `GET /me/clans` lists approved memberships only (`backend/app/api/v1/me.py`), so one row
      // here is one approved membership, and a pending one would read as an empty list.
      const clans = await myClans(request, invitee.access_token)
      expect(clans.map(({ clan_id, role }) => ({ clan_id, role }))).toEqual([
        { clan_id: clanId, role: INVITED_ROLE },
      ])
    })

    const spent = walk.requests.filter(({ url }) => {
      const { origin, pathname } = new URL(url)
      return (
        origin === authStackInputs().apiOrigin &&
        (pathname.startsWith('/api/v1/auth') || pathname.startsWith('/api/v1/invitations'))
      )
    })
    test.info().annotations.push({
      type: 'rate-limit budget',
      description: `${spent.length} browser requests under /api/v1/auth and /api/v1/invitations: ${spent
        .map((r) => `${r.method} ${new URL(r.url).pathname.replace(token, '<token>')}`)
        .join(', ')}`,
    })
  })
})
