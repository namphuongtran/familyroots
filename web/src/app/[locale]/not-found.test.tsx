import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { expected, renderWithProviders } from '@/shared/testing/render'
import NotFound from './not-found'
import viMessages from '../../../messages/vi.json'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import frMessages from '../../../messages/fr.json'

/** #366: the 404 reads in the route's locale and links back into the app under that locale. */
const CASES = [
  ['vi', viMessages],
  ['en', enMessages],
  ['zh', zhMessages],
  ['fr', frMessages],
] as const

describe('localized 404', () => {
  it.each(CASES)('renders the %s copy and a link back', (locale, messages) => {
    renderWithProviders(<NotFound />, { locale, messages })
    expect(screen.getByRole('heading', { name: expected(messages.notFound.title) })).toBeVisible()
    expect(screen.getByText(expected(messages.notFound.body))).toBeVisible()
    expect(screen.getByRole('link', { name: expected(messages.notFound.back) })).toHaveAttribute(
      'href',
      `/${locale}/dashboard`,
    )
  })
})
