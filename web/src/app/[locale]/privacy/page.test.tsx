import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { expected, renderWithProviders } from '@/shared/testing/render'
import PrivacyPage from './page'
import enMessages from '../../../../messages/en.json'
import viMessages from '../../../../messages/vi.json'

/**
 * #333: the privacy notice page carries a visible draft banner until the legal review (#322)
 * closes. The page is rendered under the real vi and en locale files and read as a person reads
 * it: the banner by its text, the title and sections by heading role.
 *
 * Negative control, 2026-11-21, with the banner `<p>` deleted from `page.tsx`: both locale cases
 * failed with `Unable to find an element with the text: Bản nháp — cần rà soát pháp lý` (and
 * `Draft — pending legal review` under en), the rest of the page printed in the DOM.
 */

const CASES = [
  { locale: 'vi', messages: viMessages },
  { locale: 'en', messages: enMessages },
] as const

describe.each(CASES)('the privacy notice under $locale', ({ locale, messages }) => {
  it('shows the draft banner', () => {
    renderWithProviders(<PrivacyPage />, { locale, messages })

    expect(screen.getByText(expected(messages.privacy.draft_banner))).toBeVisible()
  })

  it('reads as a titled document with its sections', () => {
    renderWithProviders(<PrivacyPage />, { locale, messages })

    expect(
      screen.getByRole('heading', { level: 1, name: expected(messages.privacy.title) }),
    ).toBeInTheDocument()
    for (const key of [
      'collect_title',
      'visibility_title',
      'rights_title',
      'contact_title',
    ] as const) {
      expect(
        screen.getByRole('heading', { level: 2, name: expected(messages.privacy[key]) }),
      ).toBeInTheDocument()
    }
  })
})

describe('the draft banner wording', () => {
  // Literal on purpose: #333 fixes the Vietnamese wording.
  it('is the one the issue asks for under vi', () => {
    renderWithProviders(<PrivacyPage />, { locale: 'vi', messages: viMessages })

    expect(screen.getByText('Bản nháp — cần rà soát pháp lý')).toBeVisible()
  })
})
