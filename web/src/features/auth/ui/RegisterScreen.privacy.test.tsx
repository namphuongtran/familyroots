import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { RegisterScreen } from './RegisterScreen'
import enMessages from '../../../../messages/en.json'
import viMessages from '../../../../messages/vi.json'

/**
 * #333: sign-up links to the privacy notice. The link is read by its accessible name (the words
 * inside the sentence) and its href, under vi and en.
 *
 * Mocks only `next/navigation`, as `RegisterScreen.google.test.tsx` does.
 *
 * Negative control, 2026-11-21, with the notice paragraph deleted from `RegisterScreen.tsx`: both
 * cases failed with `Unable to find an accessible element with the role "link" and name
 * "thông báo quyền riêng tư"` (and `privacy notice` under en).
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

/** The words inside `<link>…</link>` in the message. */
function linkText(message: string): string {
  const match = /<link>(.*)<\/link>/.exec(expected(message))
  if (!match) throw new Error('the message has no <link> tag')
  return match[1]
}

describe.each([
  { locale: 'vi', messages: viMessages },
  { locale: 'en', messages: enMessages },
] as const)('the register screen under $locale', ({ locale, messages }) => {
  it('links to the privacy notice', () => {
    renderWithProviders(<RegisterScreen />, { locale, messages })

    const link = screen.getByRole('link', { name: linkText(messages.privacy.signup_notice) })
    expect(link.getAttribute('href')).toBe(`/${locale}/privacy`)
  })
})
