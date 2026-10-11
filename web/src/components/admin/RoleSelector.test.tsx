import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { expected, renderWithProviders } from '@/shared/testing/render'
import enMessages from '../../../messages/en.json'
import zhMessages from '../../../messages/zh.json'
import { RoleSelector } from './RoleSelector'

/**
 * #233: each button asked the `admin` namespace for `role.viewer` and `role.viewer_desc`, but
 * `admin.role` is the string "Role" and no role description existed, so every locale read the key
 * path. The names now reuse `admin.viewer`, `admin.editor` and `admin.admin_role`, and the
 * descriptions are new keys. The six readings below are every message the selector asks for, so a
 * key that does not resolve fails one of them.
 *
 * Negative control, 2026-10-11, with the description keys in all four locale files and the
 * selector still asking for `role.*`: every case failed, the buttons named
 * `admin.role.viewer admin.role.viewer_desc`, `admin.role.editor admin.role.editor_desc` and
 * `admin.role.admin admin.role.admin_desc`.
 */

const LOCALES = [
  { locale: 'en', messages: enMessages },
  { locale: 'zh', messages: zhMessages },
] as const

describe.each(LOCALES)('the role selector, under the $locale locale', ({ locale, messages }) => {
  it.each([
    ['viewer', messages.admin.viewer, messages.admin.viewer_desc],
    ['editor', messages.admin.editor, messages.admin.editor_desc],
    ['admin', messages.admin.admin_role, messages.admin.admin_role_desc],
  ])('names the %s button with its role and what that role may do', (_, name, desc) => {
    renderWithProviders(<RoleSelector value="viewer" onChange={() => {}} />, {
      locale,
      messages: messages as unknown as AbstractIntlMessages,
    })

    // The name and the description are two block elements, so the accessible name joins them
    // with a space.
    expect(
      screen.getByRole('button', { name: `${expected(name)} ${expected(desc)}` }),
    ).toBeInTheDocument()
  })
})
