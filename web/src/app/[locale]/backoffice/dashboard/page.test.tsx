import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { createTranslator } from 'next-intl'
import { expected, renderWithProviders } from '@/shared/testing/render'
import BackofficeDashboardPage from './page'
import viMessages from '../../../../../messages/vi.json'

/**
 * #197: the four stat labels were English literals, so a Vietnamese, Chinese or French admin
 * read `Total Members` over a count in their own language. The page is an async server
 * component: the case awaits the element it returns and renders it, with next-intl's own
 * `createTranslator` over the real locale file standing in for `getTranslations`
 * (`platform/layout.test.tsx`).
 *
 * Three of the four reuse a key that already says the same thing elsewhere, so the expected
 * values come from those keys.
 *
 * Negative control, 2026-10-06, with the keys in all four locale files and the page still
 * holding the literals: the case failed with `Unable to find an element with the text: Tổng số
 * thành viên`, and the printed DOM read `Total Members`.
 */

const MESSAGES = { vi: viMessages } as const

vi.mock('next-intl/server', () => ({
  getTranslations: async ({
    locale,
    namespace,
  }: {
    locale: keyof typeof MESSAGES
    namespace?: string
  }) => createTranslator({ locale, messages: MESSAGES[locale], namespace: namespace as never }),
}))

describe('the backoffice dashboard stat labels', () => {
  it('read in Vietnamese under the vi locale', async () => {
    const element = await BackofficeDashboardPage({ params: Promise.resolve({ locale: 'vi' }) })
    renderWithProviders(element, { locale: 'vi', messages: viMessages })

    for (const label of [
      viMessages.platform.total_members,
      viMessages.admin.pending_approval,
      viMessages.dashboard.documents,
      viMessages.Backoffice.stat_tree_completeness,
    ]) {
      expect(screen.getByText(expected(label))).toBeInTheDocument()
    }
  })
})
