import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/shared/testing/render'
import { SiteFooter } from './SiteFooter'
import enMessages from '../../../messages/en.json'
import viMessages from '../../../messages/vi.json'

describe('SiteFooter', () => {
  it('links to the privacy notice under the active locale (vi)', () => {
    renderWithProviders(<SiteFooter />, { locale: 'vi', messages: viMessages })

    const link = screen.getByRole('link', { name: viMessages.privacy.link })
    expect(link).toHaveAttribute('href', '/vi/privacy')
  })

  it('links to the privacy notice under the active locale (en)', () => {
    renderWithProviders(<SiteFooter />, { locale: 'en', messages: enMessages })

    const link = screen.getByRole('link', { name: enMessages.privacy.link })
    expect(link).toHaveAttribute('href', '/en/privacy')
  })
})
