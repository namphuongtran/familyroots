import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { expected, renderWithProviders } from '@/shared/testing/render'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import { RoleSelector } from './RoleSelector'

/**
 * #233: each button asked the `admin` namespace for `role.viewer` and `role.viewer_desc`, but
 * `admin.role` is the string "Role" and no role description existed, so every locale read the key
 * path. The names now reuse `admin.viewer`, `admin.editor` and `admin.admin_role`; the descriptions
 * are new keys, worded from the permission matrix in `docs/architecture/rbac.md`.
 */

const LOCALES = [
  { locale: 'en', messages: enMessages },
  { locale: 'zh', messages: zhMessages },
] as const

afterEach(() => {
  vi.restoreAllMocks()
})

describe.each(LOCALES)('the role selector, under the $locale locale', ({ locale, messages }) => {
  function renderSelector() {
    renderWithProviders(<RoleSelector value="viewer" onChange={() => {}} />, {
      locale,
      messages: messages as unknown as AbstractIntlMessages,
    })
  }

  it.each([
    ['viewer', () => messages.admin.viewer, () => messages.admin.viewer_desc],
    ['editor', () => messages.admin.editor, () => messages.admin.editor_desc],
    ['admin', () => messages.admin.admin_role, () => messages.admin.admin_role_desc],
  ])('names the %s button with its role and what that role may do', (_, name, desc) => {
    renderSelector()

    // The name and the description are two block elements, so the accessible name joins them
    // with a space.
    expect(
      screen.getByRole('button', { name: `${expected(name())} ${expected(desc())}` }),
    ).toBeInTheDocument()
  })

  it('resolves every message it asks for', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})

    renderSelector()

    expect(error).not.toHaveBeenCalled()
  })
})
