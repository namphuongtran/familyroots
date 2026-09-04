import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth, useAuthActions } from '@/lib/hooks/useAuth'
import { renderWithProviders } from '@/shared/testing/render'
import RegisterPage from './page'
import messages from '../../../../../messages/vi.json'

/**
 * the clan-code spec, spec § 7.1b: the clan code is "auto-suggested, slugified live from the
 * name, editable", and `auth.clan_slug_taken` renders inline on the code field with a
 * suggested alternative.
 *
 * **The web register form added the last three describe blocks**, for the join half of the same
 * screen: the field submits `clan_code`, its helper text is spec § 7.1b's, and
 * `clan_not_found` renders inline on it rather than in the page-level banner.
 *
 * These assertions read the **value in the field**, per `.claude/rules/testing.md` §
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

/**
 * The envelope shape the legacy axios client rejects with, for any backend error code.
 * The web register form generalised this out of `clanSlugTakenRejection` so the join half's 404 is built
 * the same way rather than by a second hand-written literal.
 */
function backendRejection(status: number, code: string, message: string) {
  return { response: { status, data: { error: { code, message, detail: {} } } } }
}

function clanSlugTakenRejection() {
  return backendRejection(409, 'auth.clan_slug_taken', BACKEND_VI_TAKEN_MESSAGE)
}

/**
 * `_resolve_join_target` raises `EntityNotFoundError("clan_not_found")` at
 * `backend/app/application/auth/handlers.py:147`, which `app_exception_handler` turns into
 * a 404 with the generic message at `backend/app/i18n/vi.json:4`. The generic wording is
 * quoted here on purpose: the assertions below require the screen to show spec § 7.1b's
 * own sentence instead, so a test that accepted the backend message would pass on the
 * wrong string.
 */
const BACKEND_VI_CLAN_NOT_FOUND_MESSAGE = 'Không tìm thấy dòng họ'

function clanNotFoundRejection() {
  return backendRejection(404, 'clan_not_found', BACKEND_VI_CLAN_NOT_FOUND_MESSAGE)
}

/** Join is the mode the screen opens in, so this renders and touches nothing else. */
function renderJoinMode(signUp = vi.fn()) {
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
  return { ...rendered, signUp }
}

function renderCreateMode(signUp = vi.fn()) {
  const rendered = renderJoinMode(signUp)
  // "Tạo dòng họ mới" — messages.auth.create_clan.
  fireEvent.click(screen.getByLabelText(messages.auth.create_clan))
  return rendered
}

/**
 * The full-name, email, and password inputs carry no `id`/`htmlFor` pair, so
 * `getByLabelText` cannot see them. They are shared by this screen's join half (seed
 * the web register form) and its OAuth-onboarding mode, so the clan-code spec left them alone rather than reach
 * outside the create branch it owns. This walks label → containing block → input, the
 * same way `select-clan/page.test.tsx` walks around the radio labels there.
 *
 * The two clan fields deliberately do **not** go through this: they use
 * `getByLabelText`, so the label association the clan-code spec added is itself asserted.
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

/* ── the web register form: the join half ─────────────────────────────────────────────── */

function submitJoin() {
  fireEvent.click(screen.getByRole('button', { name: messages.auth.register }))
}

describe('register, join mode: the clan code field', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the helper text spec § 7.1b asks for, tied to the field', () => {
    renderJoinMode()

    const helper = screen.getByText(messages.auth.clan_slug_join_helper)
    expect(helper).toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-describedby')).toContain(helper.id)
  })

  it('offers no placeholder, so nothing on screen still asks for a UUID', () => {
    renderJoinMode()

    expect(clanCodeField().getAttribute('placeholder')).toBeNull()
  })

  it('submits the code as clan_code, and does not submit clan_id', async () => {
    const { signUp } = renderJoinMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanCodeField(), { target: { value: 'nguyen-huu-thanh-oai' } })
    submitJoin()

    await waitFor(() => expect(signUp).toHaveBeenCalled())
    const body = signUp.mock.calls[0][0] as Record<string, unknown>
    expect(body.clan_code).toBe('nguyen-huu-thanh-oai')
    expect(body.clan_action).toBe('join')
    // Both together is a 422 `auth.clan_code_and_id_both_given`
    // (`docs/contracts/rest-auth-api.md`, "The join identifier"), so the absence is the
    // assertion, not a tidiness preference.
    expect('clan_id' in body).toBe(false)
  })

  it('trims a pasted code rather than sending the whitespace', async () => {
    const { signUp } = renderJoinMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanCodeField(), { target: { value: '  nguyen-huu-thanh-oai\n' } })
    submitJoin()

    await waitFor(() => expect(signUp).toHaveBeenCalled())
    expect((signUp.mock.calls[0][0] as Record<string, unknown>).clan_code).toBe(
      'nguyen-huu-thanh-oai',
    )
  })
})

describe('register, join mode: clan_not_found', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function submitAndMiss() {
    const rendered = renderJoinMode(vi.fn().mockRejectedValue(clanNotFoundRejection()))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanCodeField(), { target: { value: 'khong-co-dong-ho-nay' } })
    submitJoin()

    await waitFor(() => expect(rendered.signUp).toHaveBeenCalled())
    return rendered
  }

  it('renders spec § 7.1b wording on the code field, not in the page-level banner', async () => {
    await submitAndMiss()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(messages.auth.clan_slug_not_found)

    // "on the field" is the claim, so assert the relationship: the alert is the element
    // the input names, and it sits inside the input's own block.
    const field = clanCodeField()
    expect(field.getAttribute('aria-describedby')).toContain(alert.id)
    expect(field.getAttribute('aria-invalid')).toBe('true')
    expect(field.closest('div')!.contains(alert)).toBe(true)

    // The page-level banner is what this failure used to reach. `register_error` is the
    // copy it would show for a non-Error rejection, so its absence is the discriminator.
    expect(screen.queryByText(messages.auth.register_error)).not.toBeInTheDocument()
    // And the backend's generic wording is not what spec § 7.1b asks the field to say.
    expect(screen.queryByText(BACKEND_VI_CLAN_NOT_FOUND_MESSAGE)).not.toBeInTheDocument()
  })

  it('clears the inline error at the start of the next submit', async () => {
    const { signUp } = await submitAndMiss()
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    // A different failure on the second attempt, so the form is still on screen and the
    // reading is "the inline error went away", not "the success screen replaced it".
    signUp.mockReset()
    signUp.mockRejectedValue(new Error('boom'))
    fireEvent.change(clanCodeField(), { target: { value: 'nguyen-huu-thanh-oai' } })
    submitJoin()

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-invalid')).toBeNull()
  })

  it('leaves the page-level banner alone for any other failure', async () => {
    renderJoinMode(vi.fn().mockRejectedValue(new Error('boom')))

    fillTheFieldsThisSeedDoesNotOwn()
    fireEvent.change(clanCodeField(), { target: { value: 'nguyen-huu-thanh-oai' } })
    submitJoin()

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-invalid')).toBeNull()
  })
})

describe('register, join mode: a code the backend would refuse on shape', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('never reaches the network, and says so on the field', async () => {
    const { signUp } = renderJoinMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fillTheFieldsThisSeedDoesNotOwn()
    // A space and capitals: `^[a-z0-9]+(?:-[a-z0-9]+)*$` refuses both, so the backend
    // would answer 422 `validation_error` with no copy a person can read.
    fireEvent.change(clanCodeField(), { target: { value: 'Nguyen Huu Thanh Oai' } })
    submitJoin()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(messages.auth.clan_slug_invalid)
    expect(clanCodeField().getAttribute('aria-invalid')).toBe('true')
    expect(signUp).not.toHaveBeenCalled()
  })
})
