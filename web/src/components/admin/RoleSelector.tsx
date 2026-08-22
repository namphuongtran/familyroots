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

// ADR-055: `editor` used to be `bg-blue-50 text-blue-700 border-blue-300`, a
// hardcoded blue with no token and no dark value. Each role's own label is
// already the identifying channel (T-06), so the colour here is reinforcing,
// not the only signal — no new token was defended for a third state between
// the existing neutral `viewer` and elevated-risk `destructive` `admin`.
// `editor` takes the already-tokened, already-AA-gated `primary-container`
// pair instead: the leaf-green "this is the normal collaborating role".
const ROLE_COLORS: Record<ClanRole, string> = {
  viewer: 'bg-muted text-foreground border-input',
  editor: 'bg-primary-container text-primary-container-foreground border-primary',
  admin: 'bg-destructive/10 text-destructive border-destructive/30',
}

export function RoleSelector({ value, onChange, disabled }: RoleSelectorProps) {
  const t = useTranslations('admin')

  return (
    <div className="flex flex-col gap-1.5">
      {ROLES.map((role) => (
        <button
          key={role.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(role.value)}
          className={cn(
            'flex items-start gap-2 rounded-lg border px-3 py-2 text-left transition-all',
            value === role.value
              ? ROLE_COLORS[role.value]
              : 'border-border bg-card text-muted-foreground hover:border-input',
            disabled && 'cursor-not-allowed opacity-50',
          )}
        >
          <div className="flex-1">
            <p className="text-sm font-medium">{t(role.labelKey)}</p>
            <p className="text-[11px] opacity-70">{t(role.descKey)}</p>
          </div>
          {value === role.value && (
            <span className="mt-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-current">
              <span className="h-2 w-2 rounded-full bg-current" />
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
