import { cn } from '@/lib/utils/cn'
import { InitialsAvatar, type InitialsAvatarSize } from '@/shared/ui/InitialsAvatar'

interface PersonAvatarProps {
  fullName: string
  avatarUrl?: string | null
  size?: 'xs' | 'sm' | 'md' | 'lg'
  isDeceased?: boolean
  className?: string
}

/**
 * The physical size behind each name. `InitialsAvatar`'s doc comment says why
 * every size is pinned in pixels rather than `rem`.
 */
const SIZE_PX: Record<NonNullable<PersonAvatarProps['size']>, InitialsAvatarSize> = {
  xs: 32,
  sm: 40,
  md: 56,
  lg: 96,
}

/**
 * `size="sm"` (40px) is the row size spec §7.5 names; `"lg"` (96px) is the
 * profile header size spec §7.6 names. `"xs"` (32px) is the tree node's,
 * the size `MemberNode` drew before it moved onto this component. No
 * gender-coded background: the legacy `components/members/MemberAvatar.tsx`
 * used `bg-blue-100`/`bg-rose-100`, a hardcoded palette with no dark value
 * (`.claude/rules/tailwind.md` §3) — `InitialsAvatar` uses
 * `bg-muted`/`text-foreground` instead, which is themed either way.
 */
export function PersonAvatar({
  fullName,
  avatarUrl,
  size = 'md',
  isDeceased = false,
  className,
}: PersonAvatarProps) {
  return (
    <InitialsAvatar
      name={fullName}
      imageUrl={avatarUrl}
      size={SIZE_PX[size]}
      className={cn(isDeceased && 'opacity-70', className)}
    />
  )
}
