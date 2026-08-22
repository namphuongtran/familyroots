'use client'

import { cn } from '@/lib/utils/cn'

interface MemberAvatarProps {
  avatarUrl?: string
  fullName: string
  gender: 'male' | 'female' | 'unknown'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  isDeceased?: boolean
  className?: string
}

const SIZE_CLASSES = {
  xs: 'h-6 w-6 text-[9px]',
  sm: 'h-8 w-8 text-xs',
  md: 'h-10 w-10 text-sm',
  lg: 'h-14 w-14 text-base',
}

/**
 * ADR-055 removed the per-gender fill this used to hold
 * (`bg-blue-100 text-blue-700` male, `bg-rose-100 text-rose-700` female).
 * Nothing on this avatar carries gender through text or an icon, so colour
 * was T-06's forbidden *only* channel, and the two hexes could not flip with
 * the colour scheme besides. Every avatar now takes the one neutral fill the
 * `'unknown'` case already used. `gender` stays a prop — every caller already
 * passes it and a future icon-based indicator would still need it — but a
 * `data-gender` attribute is the only place it reaches the DOM today.
 */
const AVATAR_FILL = 'bg-muted text-muted-foreground'

function getInitials(fullName: string): string {
  return fullName
    .split(' ')
    .filter(Boolean)
    .slice(-2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

export function MemberAvatar({
  avatarUrl,
  fullName,
  gender,
  size = 'md',
  isDeceased = false,
  className,
}: MemberAvatarProps) {
  return (
    <span
      data-gender={gender}
      className={cn(
        'relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold',
        SIZE_CLASSES[size],
        !avatarUrl && AVATAR_FILL,
        isDeceased && 'opacity-60 grayscale',
        className,
      )}
    >
      {avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={avatarUrl} alt={fullName} className="h-full w-full object-cover" />
      ) : (
        <span>{getInitials(fullName)}</span>
      )}
      {isDeceased && <span className="absolute inset-0 rounded-full bg-white/20" />}
    </span>
  )
}
