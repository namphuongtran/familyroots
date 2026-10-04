import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AbstractIntlMessages } from 'next-intl'
import { useAuthActions } from '@/features/auth'
import { renderWithProviders } from '@/shared/testing/render'
import { BackofficeSidebar } from './BackofficeSidebar'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import viMessages from '../../../messages/vi.json'

/**
 * the logout-label fix. `BackofficeSidebar.tsx:84` carried the literal `Sign out` as the button's only text,
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

vi.mock('@/features/auth', () => ({ useAuthActions: vi.fn() }))
vi.mock('next/navigation', () => ({ usePathname: () => '/vi/backoffice/dashboard' }))
vi.mock('next/link', () => ({
  // `onClick` passes through, because the drawer closes on it. The default is prevented after
  // it runs, so jsdom does not log "navigation not implemented" for every click.
  default: ({
    href,
    children,
    onClick,
  }: {
    href: string
    children: React.ReactNode
    onClick?: React.MouseEventHandler<HTMLAnchorElement>
  }) => (
    <a
      href={href}
      onClick={(event) => {
        onClick?.(event)
        event.preventDefault()
      }}
    >
      {children}
    </a>
  ),
}))

const mockUseAuthActions = vi.mocked(useAuthActions)

function renderSidebar(locale: string, messages: AbstractIntlMessages) {
  mockUseAuthActions.mockReturnValue({ signOut: vi.fn() } as unknown as ReturnType<
    typeof useAuthActions
  >)
  renderWithProviders(<BackofficeSidebar locale={locale} />, { locale, messages })
}

function renderRail(locale: string, messages: AbstractIntlMessages) {
  renderSidebar(locale, messages)
  // The rail's only <button> is sign out; every nav entry is a link. The top bar's menu button
  // sits outside the `aside`, as it does in a browser.
  return within(screen.getByRole('complementary')).getByRole('button')
}

describe('BackofficeSidebar sign-out label', () => {
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

/**
 * #174. Below `lg` the rail lives in a modal drawer behind a menu button. jsdom has no layout
 * engine, so nothing here measures a box: the four geometry readings are
 * `e2e/auth/backoffice.auth.spec.ts`'s. These cases read what the drawer does when it is used.
 *
 * Negative controls, run 2026-10-04 and reverted: rendering the drawer's body without
 * `onNavigate` failed "closes when a link is chosen", and adding
 * `onEscapeKeyDown={(event) => event.preventDefault()}` to the drawer, `StaleWriteDialog`'s
 * refusal, failed "closes on Escape". Planted together, exactly those two failed and the other
 * six stayed green.
 */
describe('BackofficeSidebar drawer', () => {
  const RAIL_LABELS = [
    viMessages.Backoffice.nav_dashboard,
    viMessages.Backoffice.nav_members,
    viMessages.Backoffice.nav_clans,
    viMessages.Backoffice.nav_tree,
  ]

  async function openDrawer() {
    renderSidebar('vi', viMessages)
    const user = userEvent.setup()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: viMessages.Backoffice.menu_open }))
    return { user, drawer: await screen.findByRole('dialog') }
  }

  it('opens on the named menu button, holding the four links, sign-out and a named close', async () => {
    const { drawer } = await openDrawer()

    for (const label of RAIL_LABELS) {
      expect(within(drawer).getByRole('link', { name: label })).toBeVisible()
    }
    expect(within(drawer).getByRole('button', { name: viMessages.auth.logout })).toBeVisible()
    expect(within(drawer).getByRole('button', { name: viMessages.common.close })).toBeVisible()
  })

  it('closes when a link is chosen', async () => {
    const { user, drawer } = await openDrawer()

    await user.click(within(drawer).getByRole('link', { name: viMessages.Backoffice.nav_members }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('closes on Escape, because a navigation drawer has nothing to lose on dismiss', async () => {
    const { user } = await openDrawer()

    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('closes on its close button', async () => {
    const { user, drawer } = await openDrawer()

    await user.click(within(drawer).getByRole('button', { name: viMessages.common.close }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
