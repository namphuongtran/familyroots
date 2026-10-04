import { fireEvent, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import RegisterPage from './page'
import messages from '../../../../../messages/vi.json'

/**
 * #182: a successful registration used to show the user nothing. The repository returned
 * the whole `{"data": {"message": …}}` body, so the page's `result.message` was
 * `undefined`, `setSuccess(undefined)` left `success` falsy, and the success screen never
 * rendered. `page.test.tsx` could not see it: it mocks `useAuthActions`, so its `signUp`
 * resolves whatever the test hands it.
 *
 * This file mocks one module, `next/navigation`, because jsdom has no App Router. The real
 * `useAuthActions` runs, the real repository sends the request, and MSW answers with the
 * body `backend/app/api/v1/auth.py`'s `register` route sends: a 201 with
 * `{"data": {"message": t("auth.registration_received")}}`, typed by the generated
 * `MessageData` so it cannot drift from the schema without failing `pnpm type-check`.
 *
 * #183 rewrites the repository and must keep this file green **unchanged**, so it reaches
 * nothing the auth slice moves. The handler matches any origin, because the legacy axios
 * client and `apiFetch` build their base URLs from different variables. Supabase is not
 * mocked: with no stored session the browser client makes no request, so the reading is
 * the same whether or not the shell exports `NEXT_PUBLIC_SUPABASE_*`. Run both ways on
 * 2026-10-04, unset and set to placeholders: one pass each.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

/** `backend/app/i18n/vi.json:104`, `auth.registration_received`. */
const BACKEND_VI_REGISTRATION_RECEIVED =
  'Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp theo'

const registrationReceived: components['schemas']['MessageData'] = {
  message: BACKEND_VI_REGISTRATION_RECEIVED,
}

describe('register: a 201 shows the success screen', () => {
  it('renders the message the backend sent, in place of the form', async () => {
    server.use(
      http.post('*/api/v1/auth/register', () =>
        HttpResponse.json(envelope(registrationReceived), { status: 201 }),
      ),
    )
    const { container } = renderWithProviders(<RegisterPage />, { messages })

    fireEvent.change(screen.getByLabelText(messages.auth.full_name), {
      target: { value: 'Trần Văn A' },
    })
    fireEvent.change(screen.getByLabelText(messages.auth.email), {
      target: { value: 'a@example.com' },
    })
    fireEvent.change(screen.getByLabelText(messages.auth.password), {
      target: { value: 'correct horse battery' },
    })
    fireEvent.change(screen.getByLabelText(messages.auth.clan_slug), {
      target: { value: 'nguyen-huu-thanh-oai' },
    })
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    expect(await screen.findByText(BACKEND_VI_REGISTRATION_RECEIVED)).toBeInTheDocument()
    expect(container.querySelector('form')).toBeNull()
  })
})
