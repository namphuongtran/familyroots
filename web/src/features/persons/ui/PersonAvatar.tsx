import { cn } from '@/lib/utils/cn'

interface PersonAvatarProps {
  fullName: string
  avatarUrl?: string | null
  size?: 'sm' | 'md' | 'lg'
  isDeceased?: boolean
  className?: string
}

/**
 * Pixel-fixed arbitrary values, not `h-10`/`w-10`-style `rem` utilities.
 * `T-04`'s 200%-text-scale check (`e2e/text-scale.spec.ts`) simulates OS text
 * scale by setting `:root { font-size: 32px }`, and `rem` is *defined*
 * relative to that root size — so a `rem`-sized box scales right along with
 * the text. Measured on this component before this fix, in a throwaway
 * preview route (2026-08-22): a plain two-row list at 320px width and 200%
 * scale measured `scrollWidth` 382 against `clientWidth` 320, and the
 * flex-1 text column next to a `size="sm"` avatar (which had ballooned from
 * 40 to 80 physical px) was left only 72px wide — not the row's text
 * overflowing, the avatar's own box crowding it out. An avatar is
 * decorative, not the text content `T-04` is about, so it is pinned to a
 * true physical size instead; the initials text inside is pinned the same
 * way, and is clipped by `overflow-hidden` if it ever does not fit, rather
 * than growing the circle.
 */
const SIZE_CLASSES: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'h-[40px] w-[40px] text-[14px]',
  md: 'h-[56px] w-[56px] text-[16px]',
  lg: 'h-[96px] w-[96px] text-[32px]',
}

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean)
  const picked = parts.slice(-2).map((word) => word[0]?.toUpperCase() ?? '')
  return picked.join('') || '?'
}

/**
 * `size="sm"` (40px) is the row size spec §7.5 names; `"lg"` (96px) is the
 * profile header size spec §7.6 names. No gender-coded background: the
 * legacy `components/members/MemberAvatar.tsx` used `bg-blue-100`/`bg-rose-100`,
 * a hardcoded palette with no dark value (`.claude/rules/tailwind.md` §3) —
 * this uses `bg-muted`/`text-foreground` instead, which is themed either way.
 * A raw `<img>`, not `next/image`: `.claude/rules/tailwind.md` §8 names the
 * one accepted use of a raw `<img>` in this app (a person's own avatar URL,
 * which can be any registered clan's storage host and is read-only per
 * ADR-036) and that file already carries this exact exemption.
 */
export function PersonAvatar({
  fullName,
  avatarUrl,
  size = 'md',
  isDeceased = false,
  className,
}: PersonAvatarProps) {
  return (
    <span
      className={cn(
        'bg-muted text-foreground relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold',
        SIZE_CLASSES[size],
        isDeceased && 'opacity-70',
        className,
      )}
    >
      {avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- read-only, permanent public URL (ADR-036); same accepted pattern as components/members/MemberAvatar.tsx
        <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <span aria-hidden="true">{initials(fullName)}</span>
      )}
    </span>
  )
}
