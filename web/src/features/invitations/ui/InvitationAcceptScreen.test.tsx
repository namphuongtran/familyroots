import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { envelope, errorEnvelope, server as mswServer } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { InvitationAcceptScreen } from './InvitationAcceptScreen'
import messages from '../../../../messages/vi.json'

/**
 * Seed S-084. Every case below drives the real screen and reads what it rendered,
 * per `.claude/rules/seeds.md` § "A test pins an outcome, not a setting": the
 * assertions are on the Vietnamese copy from `messages/vi.json`, not on a state
 * variable or on the presence of a route file.
 *
 * The screen builds its own `RequestContext` through
 * `use-invitation-request-context.ts`, so these tests drive that hook through its
 * real input — the Supabase browser client — rather than stubbing the hook. That is
 * the pattern `PersonsList.test.tsx` set.
 */

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

/** 43 URL-safe base64 characters, the shape `secrets.token_urlsafe(32)` produces. */
const TOKEN = 'Zx-9Qa_bC3dEfGhIjKlMnOpQrStUvWxYz0123456789'

const CLAN_ID = '6f1c4f7e-0000-4000-8000-000000000001'

const { createClientOrNull } = vi.hoisted(() => ({ createClientOrNull: vi.fn() }))

vi.mock('@/lib/supabase/client', () => ({ createClientOrNull }))

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

/** A signed-in browser: `getClientRequestContext` finds an access token. */
function signedIn(): void {
  createClientOrNull.mockReturnValue({
    auth: { getSession: async () => ({ data: { session: { access_token: 'tok-1' } } }) },
  })
}

/** A signed-out browser: no Supabase client at all, so no access token. */
function signedOut(): void {
  createClientOrNull.mockReturnValue(null)
}

function acceptRespondsWith(response: Response | Promise<Response>): void {
  mswServer.use(http.post(`${API}/invitations/:token/accept`, () => response))
}

function refusal(code: string, status: number): Response {
  // The message is deliberately a *wrong-looking* sentence: the UI must branch on
  // `code` and never on `message` (`web/CLAUDE.md`), and a screen that read the
  // message would render this string at the user.
  return HttpResponse.json(errorEnvelope(code, 'do not render me'), { status })
}

function render() {
  return renderWithProviders(<InvitationAcceptScreen token={TOKEN} locale="vi" />, { messages })
}

/** Presses Accept, once the one-shot session resolve has enabled it. */
async function pressAccept(): Promise<void> {
  const button = await screen.findByRole('button', { name: 'Tham gia dòng họ' })
  await waitFor(() => expect(button).toBeEnabled())
  await userEvent.click(button)
}

describe('the invitation page — the four contract outcomes', () => {
  it('accepted: renders the joined-the-clan state and the granted role', async () => {
    signedIn()
    acceptRespondsWith(
      HttpResponse.json(envelope({ clan_id: CLAN_ID, role: 'editor', message: 'ignored' })),
    )
    render()

    await pressAccept()

    expect(await screen.findByText('Bạn đã tham gia dòng họ')).toBeInTheDocument()
    expect(
      screen.getByText('Chúng tôi đã thêm bạn vào dòng họ. Hãy chọn dòng họ để bắt đầu.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Vai trò của bạn: Chỉnh sửa')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chọn dòng họ' })).toHaveAttribute(
      'href',
      '/vi/select-clan',
    )
  })

  /**
   * **The planted wrong-email control.** This is the failure that matters and the
   * one a "the page renders" test would miss: a token that is real, a session that
   * is real, and an invited email that is somebody else's. The backend refuses with
   * `invitation.email_mismatch` (`docs/contracts/error-codes.md:148`,
   * `backend/app/domain/invitation/entity.py:121-122`), and the page must refuse
   * too. The second assertion is the important half — the success copy must be
   * absent, not merely accompanied by an error.
   */
  it('email_mismatch: refuses the invitation and shows no success copy anywhere', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.email_mismatch', 403))
    render()

    await pressAccept()

    expect(await screen.findByText('Lời mời dành cho email khác')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Lời mời này được gửi tới một địa chỉ email khác với tài khoản bạn đang đăng nhập. ' +
          'Hãy đăng nhập bằng địa chỉ email đã nhận lời mời, rồi mở lại liên kết.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Bạn đã tham gia dòng họ')).not.toBeInTheDocument()
    expect(screen.queryByText(/Vai trò của bạn/)).not.toBeInTheDocument()
    // T-17: a refusal is never a dead end.
    expect(screen.getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/vi/login')
  })

  it('does not render the backend-supplied message, only its own copy', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.email_mismatch', 403))
    render()

    await pressAccept()

    await screen.findByText('Lời mời dành cho email khác')
    expect(screen.queryByText('do not render me')).not.toBeInTheDocument()
  })

  it('expired: tells the invitee to ask for a new invitation', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.expired', 409))
    render()

    await pressAccept()

    expect(await screen.findByText('Lời mời đã hết hạn')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Liên kết này đã quá hạn. Hãy nhờ quản trị viên dòng họ gửi cho bạn một lời mời mới.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Bạn đã tham gia dòng họ')).not.toBeInTheDocument()
  })

  it('not_pending: says the invitation was already used or revoked', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.not_pending', 409))
    render()

    await pressAccept()

    expect(await screen.findByText('Lời mời không còn hiệu lực')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Lời mời này đã được dùng hoặc đã bị thu hồi. Hãy nhờ quản trị viên dòng họ gửi một lời mời mới.',
      ),
    ).toBeInTheDocument()
  })

  /**
   * The three 409s above and below are the reason `refusalFor` reads the code
   * before the status. Rendered side by side here so a future edit that collapses
   * them into one "conflict" panel is caught.
   */
  it('the three 409 codes render three different headings', async () => {
    const headings: string[] = []
    for (const [code, expected] of [
      ['invitation.expired', 'Lời mời đã hết hạn'],
      ['invitation.not_pending', 'Lời mời không còn hiệu lực'],
      ['invitation.already_member', 'Bạn đã là thành viên'],
    ] as const) {
      signedIn()
      acceptRespondsWith(refusal(code, 409))
      const view = render()
      await pressAccept()
      headings.push((await screen.findByText(expected)).textContent ?? '')
      view.unmount()
      mswServer.resetHandlers()
    }

    expect(new Set(headings).size).toBe(3)
  })

  it('already_member: routes into the clan, which is what error-codes.md:147 asks for', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.already_member', 409))
    render()

    await pressAccept()

    expect(await screen.findByText('Bạn đã là thành viên')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chọn dòng họ' })).toHaveAttribute(
      'href',
      '/vi/select-clan',
    )
  })

  it('not_found: treats an unknown token as an invalid link', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.not_found', 404))
    render()

    await pressAccept()

    expect(await screen.findByText('Liên kết không hợp lệ')).toBeInTheDocument()
  })
})

describe('the invitation page — the fifth outcome: there is no session', () => {
  /**
   * `POST /invitations/{token}/accept` depends on `get_current_user`
   * (`backend/app/api/v1/invitations.py:96`) and the contract marks the row
   * `Auth | Yes` (`docs/contracts/rest-invitations-api.md:62-64`). A signed-out
   * visitor is therefore shown the sign-in state instead of a button whose only
   * possible answer is 401.
   */
  it('signed out: asks the visitor to sign in and never offers the Accept button', async () => {
    signedOut()
    render()

    expect(await screen.findByText('Hãy đăng nhập trước')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Bạn cần đăng nhập bằng địa chỉ email đã nhận lời mời. Sau khi đăng nhập, hãy mở lại liên kết này.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Đăng nhập' })).toHaveAttribute('href', '/vi/login')
    expect(screen.queryByRole('button', { name: 'Tham gia dòng họ' })).not.toBeInTheDocument()
  })

  /**
   * Not the same case as above, and this is why both branches exist: the browser
   * has a token, so the button is offered, and the backend rejects it — an access
   * token that expired while the page sat open.
   */
  it('401 on accept: the same sign-in state, reached from a signed-in browser', async () => {
    signedIn()
    acceptRespondsWith(refusal('unauthorized', 401))
    render()

    await pressAccept()

    expect(await screen.findByText('Hãy đăng nhập trước')).toBeInTheDocument()
  })
})

describe('the invitation page — what it sends, and what it does when it cannot', () => {
  it('posts the token from the URL to the contract path, with no clan header', async () => {
    signedIn()
    let seenPath: string | null = null
    let seenClanHeader: string | null = null
    mswServer.use(
      http.post(`${API}/invitations/:token/accept`, ({ request }) => {
        seenPath = new URL(request.url).pathname
        seenClanHeader = request.headers.get('x-current-clan-id')
        return HttpResponse.json(envelope({ clan_id: CLAN_ID, role: 'viewer', message: 'x' }))
      }),
    )
    render()

    await pressAccept()
    await screen.findByText('Bạn đã tham gia dòng họ')

    expect(seenPath).toBe(`/api/v1/invitations/${TOKEN}/accept`)
    // `rest-invitations-api.md:72-74`: the invitee surface takes no clan header.
    expect(seenClanHeader).toBeNull()
  })

  it('accepts only when a person presses the button, never on render', async () => {
    signedIn()
    let calls = 0
    mswServer.use(
      http.post(`${API}/invitations/:token/accept`, () => {
        calls += 1
        return HttpResponse.json(envelope({ clan_id: CLAN_ID, role: 'viewer', message: 'x' }))
      }),
    )
    render()

    // Wait for the session resolve to settle, so this is "the page is fully
    // rendered and idle", not "the page has not finished loading".
    const button = await screen.findByRole('button', { name: 'Tham gia dòng họ' })
    await waitFor(() => expect(button).toBeEnabled())

    expect(calls).toBe(0)

    await userEvent.click(button)
    await screen.findByText('Bạn đã tham gia dòng họ')
    expect(calls).toBe(1)
  })

  it('a transport failure offers a retry, and the retry can succeed', async () => {
    signedIn()
    let attempt = 0
    mswServer.use(
      http.post(`${API}/invitations/:token/accept`, () => {
        attempt += 1
        if (attempt === 1) return HttpResponse.error()
        return HttpResponse.json(envelope({ clan_id: CLAN_ID, role: 'admin', message: 'x' }))
      }),
    )
    render()

    await pressAccept()

    expect(await screen.findByText('Chưa thể tham gia lúc này')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

    expect(await screen.findByText('Bạn đã tham gia dòng họ')).toBeInTheDocument()
    expect(screen.getByText('Vai trò của bạn: Quản trị')).toBeInTheDocument()
  })

  it('never puts the token on screen, in any state', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.email_mismatch', 403))
    const view = render()

    await pressAccept()
    await screen.findByText('Lời mời dành cho email khác')

    expect(view.container.textContent ?? '').not.toContain(TOKEN)
  })

  it('announces the outcome to a screen reader rather than swapping it in silently', async () => {
    signedIn()
    acceptRespondsWith(refusal('invitation.expired', 409))
    const view = render()

    await pressAccept()
    await screen.findByText('Lời mời đã hết hạn')

    const live = view.container.querySelector('[aria-live="polite"]')
    expect(live).not.toBeNull()
    expect(live?.textContent).toContain('Lời mời đã hết hạn')
  })
})
