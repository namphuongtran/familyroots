import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthActions } from '@/features/auth/hooks/use-auth-actions'
import { useSession } from '@/features/auth/hooks/use-session'
import { ApiError } from '@/shared/http/errors'
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
 * **Since #291 (ADR-075) the clan fields live on onboarding only**, `?mode=oauth` with a signed-in
 * person who holds no membership, and the choice opens on create. Sign-up asks for no clan, so
 * every clan case here renders onboarding, and the label cases read sign-up and onboarding both.
 * `features/auth/ui/RegisterScreen.onboarding.test.tsx` reads the bodies both forms send.
 *
 * These assertions read the **value in the field**, per `.claude/rules/testing.md` §
 * "A test pins an outcome, not a setting". `src/domain/clan/clan-code.test.ts` already
 * pins the transliteration; a green suite there says nothing about whether the screen
 * shows it, which is what this file is for. What it cannot reach is layout: jsdom has no
 * layout engine, so the 320px/200% reading is `e2e/register-clan-code.spec.ts`.
 *
 * The `clan_slug_taken` rejection is shaped like the real one, not invented: since #183,
 * `register` and `onboard` go through `apiFetch`, which rejects with the `ApiError` `parseErrorBody` builds
 * from the envelope. The backend raises `ConflictError("auth.clan_slug_taken")`
 * (`backend/app/application/auth/handlers.py:171`) and `app_exception_handler` turns that into
 * `{"error": {code, message, detail}}` with `message` already localised
 * (`backend/app/core/exceptions.py`). The vi wording below is copied from
 * `backend/app/i18n/vi.json:96`. `features/auth/server/auth-repository.test.ts` sends the real
 * 409 through the transport and reads the same `ApiError` back.
 */

/** `?mode=oauth` is onboarding. The sign-up cases read the bare `/register` URL. */
const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }))

vi.mock('@/features/auth/hooks/use-session', () => ({ useSession: vi.fn() }))
vi.mock('@/features/auth/hooks/use-auth-actions', () => ({ useAuthActions: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => searchParams.current,
}))

const mockUseSession = vi.mocked(useSession)
const mockUseAuthActions = vi.mocked(useAuthActions)

const BACKEND_VI_TAKEN_MESSAGE = 'Đường dẫn dòng họ đã được sử dụng'

/**
 * What `apiFetch` rejects with for any backend error code. The web register form generalised
 * this out of `clanSlugTakenRejection` so the join half's 404 is built the same way rather than
 * by a second hand-written literal.
 */
function backendRejection(status: number, code: string, message: string) {
  return new ApiError({ code, message, status })
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

function mockActions(onboard = vi.fn()) {
  mockUseAuthActions.mockReturnValue({
    register: vi.fn(),
    signInWithGoogle: vi.fn(),
    completeOnboarding: onboard,
    signInWithEmail: vi.fn(),
    signOut: vi.fn(),
  } as unknown as ReturnType<typeof useAuthActions>)
}

/** Sign-up: the bare `/register` URL, signed out. Since ADR-075 it asks for no clan. */
function renderSignUpMode() {
  searchParams.current = new URLSearchParams()
  mockUseSession.mockReturnValue({
    session: null,
    access: { kind: 'signed-out' },
    isLoading: false,
  } as unknown as ReturnType<typeof useSession>)
  mockActions()

  return renderWithProviders(<RegisterPage />, { messages })
}

/**
 * Onboarding: `?mode=oauth` and a signed-in user who still needs onboarding, from Google or,
 * since ADR-075, from any password sign-up. The email input is prefilled and disabled, there is
 * no password field, and the full name is the profile's, so nothing needs filling to submit.
 */
function renderOnboarding(onboard = vi.fn()) {
  searchParams.current = new URLSearchParams('mode=oauth')
  mockUseSession.mockReturnValue({
    session: { profile: { fullName: 'Trần Văn A', email: 'a@example.com' }, memberships: [] },
    access: { kind: 'needs-onboarding' },
    isLoading: false,
  } as unknown as ReturnType<typeof useSession>)
  mockActions(onboard)

  const rendered = renderWithProviders(<RegisterPage />, { messages })
  return { ...rendered, onboard }
}

/** Create is the choice onboarding opens on, so this renders and touches nothing else. */
function renderCreateMode(onboard = vi.fn()) {
  return renderOnboarding(onboard)
}

function renderJoinMode(onboard = vi.fn()) {
  const rendered = renderOnboarding(onboard)
  // "Tham gia dòng họ" — messages.auth.join_clan.
  fireEvent.click(screen.getByLabelText(messages.auth.join_clan))
  return rendered
}

function clanNameField() {
  return screen.getByLabelText(messages.auth.clan_name) as HTMLInputElement
}

function clanCodeField() {
  return screen.getByLabelText(messages.auth.clan_slug) as HTMLInputElement
}

/**
 * #195. The end state is "full name, email and password each take their accessible name from
 * their visible label", so every reading here is a *name* or a *focus*, never an attribute:
 * `getByLabelText` and `toHaveAccessibleName` run the accessible-name computation over the
 * rendered tree. An assertion that `htmlFor` equals an id pins the setting, and would pass
 * with the `id` missing (`.claude/rules/testing.md` § "A test pins an outcome, not a setting").
 * The login page's copy of these cases is `login/page.test.tsx`.
 *
 * Negative control, run 2026-10-04 against the page as found (no `htmlFor`/`id` on the three):
 * all nine cases failed. `getByLabelText` threw "Found a label with the text of: Họ và tên,
 * however no form control was found associated to that label."; the enumeration reported
 * `form input 0, type text`, `1, type email` and, outside OAuth onboarding, `2, type password`
 * failing `toHaveAccessibleName()`, and no other input; and after each label click
 * `document.activeElement` was `<body>`. That control ran while sign-up still carried the clan
 * fields; since ADR-075 the counts below are sign-up's three and onboarding's five or six.
 */
describe('register: the full name, email and password labels name their inputs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('querying by the visible label text returns the input it labels', () => {
    renderSignUpMode()

    const fullName = screen.getByLabelText(messages.auth.full_name)
    expect(fullName).toBeInstanceOf(HTMLInputElement)
    expect(fullName).toHaveProperty('type', 'text')

    const email = screen.getByLabelText(messages.auth.email)
    expect(email).toBeInstanceOf(HTMLInputElement)
    expect(email).toHaveProperty('type', 'email')

    const password = screen.getByLabelText(messages.auth.password)
    expect(password).toBeInstanceOf(HTMLInputElement)
    expect(password).toHaveProperty('type', 'password')
  })

  it('in onboarding, full name and the disabled email are still named by their labels', () => {
    const { container } = renderOnboarding()

    expect(screen.getByLabelText(messages.auth.full_name)).toHaveProperty('type', 'text')
    const email = screen.getByLabelText(messages.auth.email)
    expect(email).toHaveProperty('type', 'email')
    expect(email).toBeDisabled()
    // By type, not by label: an unlabelled password field would pass a label query.
    expect(container.querySelector('form input[type="password"]')).toBeNull()
  })

  // The bare matcher is right here: this case asks only whether a name exists. The case
  // above pins which name. The counts are the screen's own: sign-up's three account fields, and
  // onboarding's two, two radios, and two clan fields in create mode or one in join mode.
  it.each([
    ['sign-up', () => renderSignUpMode(), 3],
    ['onboarding, create', () => renderCreateMode(), 6],
    ['onboarding, join', () => renderJoinMode(), 5],
  ])('every input in the form has an accessible name, in %s mode', (_mode, render, count) => {
    const { container } = render()

    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('form input'))
    expect(inputs).toHaveLength(count)
    // Soft, so a failure lists every unnamed input rather than stopping at the first.
    inputs.forEach((input, index) => {
      expect.soft(input, `form input ${index}, type ${input.type}`).toHaveAccessibleName()
    })
  })

  // `document.activeElement` is read directly and the input is found by its type, not
  // through `getByLabelText`, so this reading does not fail at the same place as the first.
  // Full name has no `type`, and sign-up has no clan field after it to match the same selector.
  it.each([
    [messages.auth.full_name, 'input:not([type])'],
    [messages.auth.email, 'input[type="email"]'],
    [messages.auth.password, 'input[type="password"]'],
  ])('clicking the visible label "%s" moves focus into its input', async (labelText, selector) => {
    const user = userEvent.setup()
    const { container } = renderSignUpMode()
    const input = container.querySelector(`form ${selector}`)
    expect(input).toBeInstanceOf(HTMLInputElement)

    await user.click(screen.getByText(labelText))

    expect(document.activeElement).toBe(input)
  })

  // The disabled email is the one label that cannot move focus, so full name is the case.
  it('in onboarding, clicking the full name label moves focus into its input', async () => {
    const user = userEvent.setup()
    const { container } = renderOnboarding()
    const input = container.querySelector('form input:not([type])')
    expect(input).toBeInstanceOf(HTMLInputElement)

    await user.click(screen.getByText(messages.auth.full_name))

    expect(document.activeElement).toBe(input)
  })
})

describe('onboarding, create mode: the clan code field', () => {
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
    const { onboard } = renderCreateMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })

    fireEvent.click(screen.getByRole('button', { name: messages.auth.complete_onboarding }))

    await waitFor(() =>
      expect(onboard).toHaveBeenCalledWith(
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

describe('onboarding, create mode: auth.clan_slug_taken', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function submitAndCollide() {
    const rendered = renderCreateMode(vi.fn().mockRejectedValue(clanSlugTakenRejection()))

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })
    fireEvent.click(screen.getByRole('button', { name: messages.auth.complete_onboarding }))

    await waitFor(() => expect(rendered.onboard).toHaveBeenCalled())
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
    const { onboard } = await submitAndCollide()

    fireEvent.click(
      screen.getByRole('button', {
        name: messages.auth.clan_slug_use_suggestion.replace('{suggestion}', 'tran-gia-2'),
      }),
    )
    onboard.mockClear()
    fireEvent.click(screen.getByRole('button', { name: messages.auth.complete_onboarding }))
    await waitFor(() => expect(onboard).toHaveBeenCalled())

    expect(
      await screen.findByRole('button', {
        name: messages.auth.clan_slug_use_suggestion.replace('{suggestion}', 'tran-gia-3'),
      }),
    ).toBeInTheDocument()
  })

  it('leaves the generic page-level error alone for any other failure', async () => {
    renderCreateMode(vi.fn().mockRejectedValue(new Error('boom')))

    fireEvent.change(clanNameField(), { target: { value: 'Trần Gia' } })
    fireEvent.click(screen.getByRole('button', { name: messages.auth.complete_onboarding }))

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-invalid')).toBeNull()
  })
})

/* ── the web register form: the join half ─────────────────────────────────────────────── */

function submit() {
  fireEvent.click(screen.getByRole('button', { name: messages.auth.complete_onboarding }))
}

describe('onboarding, join mode: the clan code field', () => {
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
    const { onboard } = renderJoinMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fireEvent.change(clanCodeField(), { target: { value: 'nguyen-huu-thanh-oai' } })
    submit()

    await waitFor(() => expect(onboard).toHaveBeenCalled())
    const body = onboard.mock.calls[0][0] as Record<string, unknown>
    expect(body.clan_code).toBe('nguyen-huu-thanh-oai')
    expect(body.clan_action).toBe('join')
    // Both together is a 422 `auth.clan_code_and_id_both_given`
    // (`docs/contracts/rest-auth-api.md`, "The join identifier"), so the absence is the
    // assertion, not a tidiness preference.
    expect('clan_id' in body).toBe(false)
  })

  it('trims a pasted code rather than sending the whitespace', async () => {
    const { onboard } = renderJoinMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    fireEvent.change(clanCodeField(), { target: { value: '  nguyen-huu-thanh-oai\n' } })
    submit()

    await waitFor(() => expect(onboard).toHaveBeenCalled())
    expect((onboard.mock.calls[0][0] as Record<string, unknown>).clan_code).toBe(
      'nguyen-huu-thanh-oai',
    )
  })
})

describe('onboarding, join mode: clan_not_found', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function submitAndMiss() {
    const rendered = renderJoinMode(vi.fn().mockRejectedValue(clanNotFoundRejection()))

    fireEvent.change(clanCodeField(), { target: { value: 'khong-co-dong-ho-nay' } })
    submit()

    await waitFor(() => expect(rendered.onboard).toHaveBeenCalled())
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
    const { onboard } = await submitAndMiss()
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    // A different failure on the second attempt, so the form is still on screen and the
    // reading is "the inline error went away", not "the success screen replaced it".
    onboard.mockReset()
    onboard.mockRejectedValue(new Error('boom'))
    fireEvent.change(clanCodeField(), { target: { value: 'nguyen-huu-thanh-oai' } })
    submit()

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-invalid')).toBeNull()
  })

  it('leaves the page-level banner alone for any other failure', async () => {
    renderJoinMode(vi.fn().mockRejectedValue(new Error('boom')))

    fireEvent.change(clanCodeField(), { target: { value: 'nguyen-huu-thanh-oai' } })
    submit()

    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(clanCodeField().getAttribute('aria-invalid')).toBeNull()
  })
})

describe('onboarding, join mode: a code the backend would refuse on shape', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('never reaches the network, and says so on the field', async () => {
    const { onboard } = renderJoinMode(vi.fn().mockResolvedValue({ message: 'ok' }))

    // A space and capitals: `^[a-z0-9]+(?:-[a-z0-9]+)*$` refuses both, so the backend
    // would answer 422 `validation_error` with no copy a person can read.
    fireEvent.change(clanCodeField(), { target: { value: 'Nguyen Huu Thanh Oai' } })
    submit()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(messages.auth.clan_slug_invalid)
    expect(clanCodeField().getAttribute('aria-invalid')).toBe('true')
    expect(onboard).not.toHaveBeenCalled()
  })
})
