import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { expected, renderWithProviders } from '@/shared/testing/render'
import AdminLayout from './layout'
import enMessages from '../../../../../messages/en.json'

/**
 * #194: the admin section's banner was a Vietnamese literal, so an English, Chinese or French
 * admin read Vietnamese above every admin page. The layout guards nothing (#186), so it renders
 * as is; the case reads the text a person gets under `en`.
 *
 * Negative control, 2026-10-06, with the key in all four locale files and the layout still
 * holding the literal: `Unable to find an element with the text: Administration area – clan
 * administrators only`, with the Vietnamese sentence in the printed DOM.
 */
describe('the admin banner', () => {
  it('reads in English under the en locale', () => {
    renderWithProviders(
      <AdminLayout>
        <p>page</p>
      </AdminLayout>,
      { locale: 'en', messages: enMessages },
    )

    expect(screen.getByText(expected(enMessages.admin.area_notice))).toBeInTheDocument()
  })
})
