import { cn } from '@/lib/utils/cn'

/** The physical size of the circle, in CSS pixels. */
export type InitialsAvatarSize = 32 | 40 | 56 | 96

interface InitialsAvatarProps {
  name: string
  imageUrl?: string | null
  size: InitialsAvatarSize
  className?: string
}

/**
 * Pixel-fixed arbitrary values, not `h-10`/`w-10`-style `rem` utilities.
 * `T-04`'s 200%-text-scale check (`e2e/text-scale.spec.ts`) simulates OS text
 * scale by setting `:root { font-size: 32px }`, and `rem` is *defined*
 * relative to that root size — so a `rem`-sized box scales right along with
 * the text. Measured on `PersonAvatar` before this fix, in a throwaway
 * preview route (2026-08-22): a plain two-row list at 320px width and 200%
 * scale measured `scrollWidth` 382 against `clientWidth` 320, and the
 * flex-1 text column next to a 40px avatar (which had ballooned to 80
 * physical px) was left only 72px wide — not the row's text overflowing, the
 * avatar's own box crowding it out. An avatar is decorative, not the text
 * content `T-04` is about, so it is pinned to a true physical size instead;
 * the initials text inside is pinned the same way, and is clipped by
 * `overflow-hidden` if it ever does not fit, rather than growing the circle.
 */
const SIZE_CLASSES: Record<InitialsAvatarSize, string> = {
  32: 'h-[32px] w-[32px] text-[12px]',
  40: 'h-[40px] w-[40px] text-[14px]',
  56: 'h-[56px] w-[56px] text-[16px]',
  96: 'h-[96px] w-[96px] text-[32px]',
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const picked = parts.slice(-2).map((word) => word[0]?.toUpperCase() ?? '')
  return picked.join('') || '?'
}

/**
 * A circle holding an image, or the last two words' initials when there is
 * none. It knows nothing about persons: a pending account uses it too
 * (`components/admin/PendingUsersList.tsx`), and `PersonAvatar` in
 * `features/persons` is built on it. ADR-060 § 1 calls this a misfiled
 * primitive, which is why it left `components/members/`.
 *
 * Decorative: the name always sits beside it in text, so the image has an
 * empty `alt` and the initials are `aria-hidden`. A raw `<img>`, not
 * `next/image`: `.claude/rules/tailwind.md` §8 names the one accepted use of a
 * raw `<img>` in this app (a person's own avatar URL, which can be any
 * registered clan's storage host and is read-only per ADR-036).
 */
export function InitialsAvatar({ name, imageUrl, size, className }: InitialsAvatarProps) {
  return (
    <span
      className={cn(
        'bg-muted text-foreground relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold',
        SIZE_CLASSES[size],
        className,
      )}
    >
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- read-only, permanent public URL (ADR-036); see the doc comment above
        <img src={imageUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <span aria-hidden="true">{initials(name)}</span>
      )}
    </span>
  )
}
