import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import LoginPage from './page'
import { renderWithProviders } from '@/shared/testing/render'
import messages from '../../../../../messages/vi.json'

/**
 * the login-label fix. The end state is "every input on the sign-in screen has an accessible name
 * that comes from its visible label", so every assertion here reads a *name*, never an
 * attribute. `getByLabelText` and `toHaveAccessibleName` both run the accessible-name
 * computation over the rendered tree, which is the thing a screen reader announces.
 * Asserting `htmlFor === 'email'` would pin the attribute the fix sets, not the outcome the
 * fix exists to produce, and would still pass if the matching `id` were missing
 * (`.claude/rules/testing.md` § "A test pins an outcome, not a setting").
 *
 * Negative control, run 2026-08-26 against the parent of this commit: both cases failed.
 * `getByLabelText` reported "Found a label with the text of: Email, however no form control
 * was found associated to that label.", and the enumeration reported
 * `Expected element to have accessible name:` for each of the two inputs.
 */
vi.mock('@/lib/hooks/useAuth', () => ({
  useAuthActions: () => ({ signIn: vi.fn(), signInWithGoogle: vi.fn() }),
}))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

describe('the sign-in form labels name their inputs', () => {
  it('querying by the visible label text returns the input it labels', () => {
    renderWithProviders(<LoginPage />, { messages })

    const email = screen.getByLabelText(messages.auth.email)
    expect(email).toBeInstanceOf(HTMLInputElement)
    expect(email).toHaveAttribute('type', 'email')

    const password = screen.getByLabelText(messages.auth.password)
    expect(password).toBeInstanceOf(HTMLInputElement)
    expect(password).toHaveAttribute('type', 'password')
  })

  it('every input in the form has a non-empty accessible name', () => {
    const { container } = renderWithProviders(<LoginPage />, { messages })

    const inputs = Array.from(container.querySelectorAll('form input'))
    expect(inputs).toHaveLength(2)
    for (const input of inputs) {
      expect(input).toHaveAccessibleName()
    }
  })

  it('clicking the visible label moves focus into the input it labels', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />, { messages })

    await user.click(screen.getByText(messages.auth.password))

    expect(screen.getByLabelText(messages.auth.password)).toHaveFocus()
  })
})
