import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { SiteFooter } from './SiteFooter'
import enMessages from '../../../messages/en.json'
import viMessages from '../../../messages/vi.json'

/**
 * #333: the footer links to the privacy notice, in the route's locale. Read by the link's
 * accessible name and its href.
 *
 * Negative control, 2026-11-21, with the href hard-coded to `/vi/privacy`: the en case failed
 * with `expected '/vi/privacy' to be '/en/privacy'`.
 */
describe.each([
  { locale: 'vi', messages: viMessages },
  { locale: 'en', messages: enMessages },
] as const)('the site footer under $locale', ({ locale, messages }) => {
  it('links to the privacy notice of that locale', () => {
    renderWithProviders(<SiteFooter />, { locale, messages })

    const link = screen.getByRole('link', { name: expected(messages.privacy.footer_link) })
    expect(link.getAttribute('href')).toBe(`/${locale}/privacy`)
  })
})
