'use client'

import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils/cn'

type ClanRole = 'admin' | 'editor' | 'viewer'

interface RoleSelectorProps {
  value: ClanRole
  onChange: (role: ClanRole) => void
  disabled?: boolean
}

const ROLES: Array<{ value: ClanRole; labelKey: string; descKey: string }> = [
  { value: 'viewer', labelKey: 'role.viewer', descKey: 'role.viewer_desc' },
  { value: 'editor', labelKey: 'role.editor', descKey: 'role.editor_desc' },
  { value: 'admin', labelKey: 'role.admin', descKey: 'role.admin_desc' },
]

const ROLE_COLORS: Record<ClanRole, string> = {
  viewer: 'bg-gray-100 text-gray-700 border-gray-300',
  editor: 'bg-blue-50 text-blue-700 border-blue-300',
  admin: 'bg-red-50 text-red-700 border-red-300',
}

export function RoleSelector({ value, onChange, disabled }: RoleSelectorProps) {
  const t = useTranslations('admin')

  return (
    <div className="flex flex-col gap-1.5">
      {ROLES.map(role => (
        <button
          key={role.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(role.value)}
          className={cn(
            'flex items-start gap-2 px-3 py-2 rounded-lg border text-left transition-all',
            value === role.value
              ? ROLE_COLORS[role.value]
              : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300',
            disabled && 'opacity-50 cursor-not-allowed',
          )}
        >
          <div className="flex-1">
            <p className="text-sm font-medium">{t(role.labelKey)}</p>
            <p className="text-[11px] opacity-70">{t(role.descKey)}</p>
          </div>
          {value === role.value && (
            <span className="mt-0.5 h-4 w-4 rounded-full border-2 border-current flex items-center justify-center">
              <span className="h-2 w-2 rounded-full bg-current" />
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
