import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth, useAuthActions } from '@/lib/hooks/useAuth'
import { renderWithProviders } from '@/shared/testing/render'
import RegisterPage from './page'
import messages from '../../../../../messages/vi.json'

/**
 * Seed S-083, spec § 7.1b: the clan code is "auto-suggested, slugified live from the
 * name, editable", and `auth.clan_slug_taken` renders inline on the code field with a
 * suggested alternative.
 *
 * These assertions read the **value in the field**, per `.claude/rules/seeds.md` §
 * "A test pins an outcome, not a setting". `src/domain/clan/clan-code.test.ts` already
 * pins the transliteration; a green suite there says nothing about whether the screen
 * shows it, which is what this file is for. What it cannot reach is layout: jsdom has no
 * layout engine, so the 320px/200% reading is `e2e/register-clan-code.spec.ts`.
 *
 * The `clan_slug_taken` rejection is shaped like the real one, not invented:
 * `authProfileRepository.register` goes through the legacy axios client
 * (`src/lib/api/axios.ts:49` re-rejects the raw axios error), the backend raises
 * `ConflictError("auth.clan_slug_taken")` (`backend/app/application/auth/handlers.py:171`)
 * and `app_exception_handler` turns that into `{"error": {code, message, detail}}` with
 * `message` already localised (`backend/app/core/exceptions.py`). The vi wording below is
 * copied from `backend/app/i18n/vi.json:96`.
 */

vi.mock('@/lib/hooks/useAuth', () => ({ useAuth: vi.fn(), useAuthActions: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

const mockUseAuth = vi.mocked(useAuth)
const mockUseAuthActions = vi.mocked(useAuthActions)

const BACKEND_VI_TAKEN_MESSAGE = 'Đường dẫn dòng họ đã được sử dụng'

function clanSlugTakenRejection() {
  return {
    response: {
      status: 409,
      data: {
        error: { code: 'auth.clan_slug_taken', message: BACKEND_VI_TAKEN_MESSAGE, detail: {} },
      },
    },
  }
}

function renderCreateMode(signUp = vi.fn()) {
  mockUseAuth.mockReturnValue({
    user: null,
    isLoading: false,
    isAuthenticated: false,
    isPendingApproval: false,
    needsOnboarding: false,
  } as unknown as ReturnType<typeof useAuth>)
  mockUseAuthActions.mockReturnValue({
    signUp,
    signInWithGoogle: vi.fn(),
    completeOnboarding: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
  } as unknown as ReturnType<typeof useAuthActions>)

  const rendered = renderWithProviders(<RegisterPage />, { messages })
  // "Tạo dòng họ mới" — messages.auth.create_clan.
  fireEvent.click(screen.getByLabelText(messages.auth.create_clan))
  return { ...rendered, signUp }
}

/**
 * The full-name, email, and password inputs carry no `id`/`htmlFor` pair, so
 * `getByLabelText` cannot see them. They are shared by this screen's join half (seed
 * S-082) and its OAuth-onboarding mode, so S-083 left them alone rather than reach
 * outside the create branch it owns. This walks label → containing block → input, the
 * same way `select-clan/page.test.tsx` walks around the radio labels there.
 *
 * The two clan fields deliberately do **not** go through this: they use
 * `getByLabelText`, so the label association S-083 added is itself asserted.
 */
function unlabelledField(labelText: string) {
  const label = screen.getByText(labelText)
  const input = label.parentElement?.querySelector('input')
  if (!input) throw new Error(`no input beside the "${labelText}" label`)
  return input as HTMLInputElement
}

function fillTheFieldsThisSeedDoesNotOwn() {
  fireEvent.change(unlabelledField(messages.auth.full_name), { target: { value: 'Trần Văn A' } })
  fireEvent.change(unlabelledField(messages.auth.email), { target: { value: 'a@example.com' } })
  fireEvent.change(unlabelledField(messages.auth.password), {
    target: { value: 'correct horse battery' },
  })
}

function clanNameField() {
  return screen.getByLabelText(messages.auth.clan_name) as HTMLInputElement
}

function clanCodeField() {
  return screen.getByLabelText(messages.auth.clan_slug) as HTMLInputElement
}

describe('register, create mode: the clan code field', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fills the code live from a Vietnamese clan name, diacritics transliterated', () => {
    renderCreateMode()

    expect(clanCodeField().value).toBe('')

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })

    expect(clanCodeField().value).toBe('tran-gia')
  })

  it('keeps the D of Đ in the field, which a naive NFD strip would drop', () => {
    renderCreateMode()

    fireEvent.change(clanNameField(), { target: { value: 'Đặng Đình' } })

    expect(clanCodeField().value).toBe('dang-dinh')
  })

  it('follows the name while the code is untouched', () => {
    renderCreateMode()

    fireEvent.change(clanNameField(), { target: { value: 'Trần' } })
    expect(clanCodeField().value).toBe('tran')

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })
    expect(clanCodeField().value).toBe('tran-gia')
  })

  it('stops following the name once the person edits the code', () => {
    renderCreateMode()

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })
    fireEvent.change(clanCodeField(), { target: { value: 'tran-gia-quang-ngai' } })

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia Hà Nội' } })

    expect(clanCodeField().value).toBe('tran-gia-quang-ngai')
  })

  it('submits the derived code, not an empty string', async () => {
    const { signUp } = renderCreateMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })

    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    await waitFor(() =>
      expect(signUp).toHaveBeenCalledWith(
        expect.objectContaining({ clan_name: 'Trần Gia', clan_slug: 'tran-gia' }),
      ),
    )
  })

  it('shows the helper text spec § 7.1b asks for, tied to the field', () => {
    renderCreateMode()

    const helper = screen.getByText(messages.auth.clan_slug_helper)
    expect(helper).toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-describedby')).toContain(helper.id)
  })
})

describe('register, create mode: auth.clan_slug_taken', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function submitAndCollide() {
    const rendered = renderCreateMode(vi.fn().mockRejectedValue(clanSlugTakenRejection()))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    await waitFor(() => expect(rendered.signUp).toHaveBeenCalled())
    return rendered
  }

  it('renders the error on the code field, not as the page-level banner', async () => {
    await submitAndCollide()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(BACKEND_VI_TAKEN_MESSAGE)

    // "on the code field" is the claim, so assert the relationship, not just presence:
    // the alert is the element the input points at, and it sits in the input's own box.
    const field = clanCodeField()
    expect(field.getAttribute('aria-describedby')).toContain(alert.id)
    expect(field.getAttribute('aria-invalid')).toBe('true')
    expect(field.closest('div')!.contains(alert)).toBe(true)
  })

  it('offers a suggested alternative and applying it fills the field', async () => {
    await submitAndCollide()

    const suggestion = await screen.findByRole('button', {
      name: messages.auth.clan_slug_use_suggestion.replace('{suggestion}', 'tran-gia-2'),
    })

    fireEvent.click(suggestion)

    expect(clanCodeField().value).toBe('tran-gia-2')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('counts the suggestion up when the alternative collides too', async () => {
    const { signUp } = await submitAndCollide()

    fireEvent.click(
      screen.getByRole('button', {
        name: messages.auth.clan_slug_use_suggestion.replace('{suggestion}', 'tran-gia-2'),
      }),
    )
    signUp.mockClear()
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))
    await waitFor(() => expect(signUp).toHaveBeenCalled())

    expect(
      await screen.findByRole('button', {
        name: messages.auth.clan_slug_use_suggestion.replace('{suggestion}', 'tran-gia-3'),
      }),
    ).toBeInTheDocument()
  })

  it('leaves the generic page-level error alone for any other failure', async () => {
    renderCreateMode(vi.fn().mockRejectedValue(new Error('boom')))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })
    fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-invalid')).toBeNull()
  })
})
