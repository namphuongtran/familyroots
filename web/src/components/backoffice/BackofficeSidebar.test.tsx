import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { useAuth } from '@/lib/hooks/useAuth'
import { renderWithProviders } from '@/shared/testing/render'
import { BackofficeSidebar } from './BackofficeSidebar'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import viMessages from '../../../messages/vi.json'

/**
 * Seed S-092. `BackofficeSidebar.tsx:84` carried the literal `Sign out` as the button's only text,
 * so a Vietnamese admin read English in the rail while every other label around it was translated.
 *
 * The string resolves through the existing `auth.logout` key rather than a new `Backoffice.*` one.
 * That key already carries a real translation in all four locale files and already has three
 * callers — `Header.tsx:117`, `PendingApprovalScreen.tsx:197`, `ClanSuspendedScreen.tsx:83` — so a
 * second key for the same sentence would be a second place to drift.
 *
 * Negative control, run 2026-08-26 against the pre-fix component: the `vi` case failed with
 *
 *     Expected element to have accessible name:
 *       Đăng xuất
 *     Received:
 *       Sign out
 */

vi.mock('@/lib/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('next/navigation', () => ({ usePathname: () => '/vi/backoffice/dashboard' }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const mockUseAuth = vi.mocked(useAuth)

function renderRail(locale: string, messages: AbstractIntlMessages) {
  mockUseAuth.mockReturnValue({ signOut: vi.fn() } as unknown as ReturnType<typeof useAuth>)
  renderWithProviders(<BackofficeSidebar locale={locale} />, { locale, messages })
  // The rail's only <button> is sign out; every nav entry is a link.
  return screen.getByRole('button')
}

describe('BackofficeSidebar sign-out label (S-092)', () => {
  it('names the button in Vietnamese under the default locale', () => {
    expect(renderRail('vi', viMessages)).toHaveAccessibleName(viMessages.auth.logout)
  })

  it('names the button in Chinese under the zh locale', () => {
    expect(renderRail('zh', zhMessages)).toHaveAccessibleName(zhMessages.auth.logout)
  })

  it('names the button in English under the en locale', () => {
    expect(renderRail('en', enMessages)).toHaveAccessibleName(enMessages.auth.logout)
  })

  it('gives each locale its own word, so no locale reads as a copy of another', () => {
    const values = [viMessages.auth.logout, enMessages.auth.logout, zhMessages.auth.logout]
    expect(new Set(values).size).toBe(values.length)
  })
})
