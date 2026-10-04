import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { renderWithProviders } from '@/shared/testing/render'
import viMessages from '../../../messages/vi.json'
import { PendingUsersList } from './PendingUsersList'

const messages = viMessages as unknown as AbstractIntlMessages

describe('PendingUsersList', () => {
  it("draws each pending account's avatar from the initials of its label", () => {
    renderWithProviders(
      <PendingUsersList
        users={[{ id: 'u1', label: 'Trần Thị Bình', created_at: '2026-10-01T08:00:00Z' }]}
        onApprove={() => {}}
        onReject={() => {}}
      />,
      { messages },
    )

    expect(screen.getByText('Trần Thị Bình')).toBeInTheDocument()
    expect(screen.getByText('TB')).toBeInTheDocument()
  })
})
