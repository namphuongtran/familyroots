import { fireEvent, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { envelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { inviteeRegisterPath } from '../model/invitee-register'
import { RegisterScreen } from './RegisterScreen'
import messages from '../../../../messages/vi.json'

/**
 * #196: the register form reached from an invitation asks for no clan, and sends the body
 * ADR-058 § 1 made the invitee's: `email`, `password` and `full_name`, and nothing else.
 *
 * **What this reads is the request the form sends**, not a prop or a state variable
 * (`.claude/rules/testing.md`, "A test pins an outcome, not a setting"). The real
 * `useAuthActions` and repository run, and MSW answers with the 201 `POST /auth/register` sends:
 * `{"data": {"message": …}}`, typed by the generated `MessageData`. The handler records each body
 * as the backend would receive it. The search params are parsed out of `inviteeRegisterPath`, the
 * same builder the invitation page's link uses, so the form here is the one that link reaches.
 *
 * A body with `clan_action` and no clan field gets the join-code error from the backend, and a body
 * with a clan field and no `clan_action` is a 422 (ADR-058 § 2). So the exact key set is the
 * assertion: a key too many is the invitee stopped at the register step.
 *
 * Mocks only `next/navigation`, for the reason `register/page.success.test.tsx` gives. Supabase is
 * not mocked: with no stored session the browser client makes no request.
 */

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => searchParams.current,
}))

/** `backend/app/i18n/vi.json`, `auth.registration_received`. */
const BACKEND_VI_REGISTRATION_RECEIVED =
  'Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp theo'

const registrationReceived: components['schemas']['MessageData'] = {
  message: BACKEND_VI_REGISTRATION_RECEIVED,
}

function reachedFrom(path: string): void {
  searchParams.current = new URL(path, 'http://web.invalid').searchParams
}

/** Serves the real 201 and returns every body the form sent. */
function registerAnswers201(): Record<string, unknown>[] {
  const bodies: Record<string, unknown>[] = []
  server.use(
    http.post('*/api/v1/auth/register', async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>)
      return HttpResponse.json(envelope(registrationReceived), { status: 201 })
    }),
  )
  return bodies
}

function fillTheAccountFields(): void {
  fireEvent.change(screen.getByLabelText(messages.auth.full_name), {
    target: { value: 'Nguyễn Thị Được Mời' },
  })
  fireEvent.change(screen.getByLabelText(messages.auth.email), {
    target: { value: 'invited@example.com' },
  })
  fireEvent.change(screen.getByLabelText(messages.auth.password), {
    target: { value: 'correct horse battery' },
  })
}

describe('register, reached from an invitation', () => {
  beforeEach(() => {
    reachedFrom(inviteeRegisterPath('vi'))
  })

  it('sends exactly email, password and full_name, and shows the success screen', async () => {
    const bodies = registerAnswers201()
    const { container } = renderWithProviders(<RegisterScreen />, { messages })

    fillTheAccountFields()
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    expect(await screen.findByText(BACKEND_VI_REGISTRATION_RECEIVED)).toBeInTheDocument()
    expect(container.querySelector('form')).toBeNull()
    expect(bodies).toHaveLength(1)
    expect(Object.keys(bodies[0]).sort()).toEqual(['email', 'full_name', 'password'])
    expect(bodies[0]).toEqual({
      email: 'invited@example.com',
      password: 'correct horse battery',
      full_name: 'Nguyễn Thị Được Mời',
    })
  })

  it('asks for no clan: no join/create choice and no clan field', () => {
    renderWithProviders(<RegisterScreen />, { messages })

    expect(screen.getByText(expected(messages.auth.register_invitee_hint))).toBeInTheDocument()
    expect(screen.queryAllByRole('radio')).toHaveLength(0)
    expect(screen.queryByLabelText(messages.auth.clan_slug)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(messages.auth.clan_name)).not.toBeInTheDocument()
  })

  it('the success screen tells the person to open the invitation link again', async () => {
    registerAnswers201()
    renderWithProviders(<RegisterScreen />, { messages })

    fillTheAccountFields()
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    expect(
      await screen.findByText(expected(messages.auth.register_invitee_success_next)),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: messages.auth.login_link })).toHaveAttribute(
      'href',
      '/vi/login',
    )
  })
})

/**
 * The control the three cases above need: the same screen, reached without the marker, still
 * offers the join/create choice and still sends `clan_action`. If it did not, a form that dropped
 * the clan for everyone would pass the cases above.
 */
describe('register, reached any other way', () => {
  beforeEach(() => {
    reachedFrom('/vi/register')
  })

  it('keeps the join/create choice, and sends clan_action with the clan code', async () => {
    const bodies = registerAnswers201()
    renderWithProviders(<RegisterScreen />, { messages })

    expect(screen.getAllByRole('radio')).toHaveLength(2)
    expect(screen.getByRole('radio', { name: messages.auth.join_clan })).toBeChecked()
    expect(screen.queryByText(messages.auth.register_invitee_hint)).not.toBeInTheDocument()

    fillTheAccountFields()
    fireEvent.change(screen.getByLabelText(messages.auth.clan_slug), {
      target: { value: 'nguyen-phuc' },
    })
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    expect(await screen.findByText(BACKEND_VI_REGISTRATION_RECEIVED)).toBeInTheDocument()
    expect(bodies).toHaveLength(1)
    expect(bodies[0]).toMatchObject({ clan_action: 'join', clan_code: 'nguyen-phuc' })
    expect(screen.queryByText(messages.auth.register_invitee_success_next)).not.toBeInTheDocument()
  })
})
