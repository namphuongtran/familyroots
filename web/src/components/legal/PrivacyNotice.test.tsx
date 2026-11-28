import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/shared/testing/render'
import { PrivacyNotice } from './PrivacyNotice'
import enMessages from '../../../messages/en.json'
import viMessages from '../../../messages/vi.json'

/**
 * #333: the privacy notice is a DRAFT until #322 closes, and the draft banner is the part a
 * reader must not miss. These read the rendered text, not the message key, so a banner that is
 * rendered empty, hidden, or in the wrong locale fails here.
 */
describe('PrivacyNotice', () => {
  it('shows the Vietnamese draft banner, visibly, in vi', () => {
    renderWithProviders(<PrivacyNotice />, { locale: 'vi', messages: viMessages })

    const banner = screen.getByText('bản nháp — cần rà soát pháp lý')
    expect(banner).toBeVisible()
    expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
  })

  it('shows the English draft banner in en, and not the Vietnamese one', () => {
    renderWithProviders(<PrivacyNotice />, { locale: 'en', messages: enMessages })

    expect(screen.getByText('Draft — pending legal review')).toBeVisible()
    expect(screen.queryByText('bản nháp — cần rà soát pháp lý')).toBeNull()
  })

  it('names the hosting region, account deletion and anonymisation, and leaves the controller pending', () => {
    renderWithProviders(<PrivacyNotice />, { locale: 'en', messages: enMessages })

    const text = document.body.textContent ?? ''
    expect(text).toContain('ap-southeast-1')
    expect(text).toContain('Singapore')
    expect(text).toContain('Đã ẩn danh')
    expect(text).toMatch(/last admin/i)
    expect(text).toMatch(/controller.*pending/i)
  })
})
